from __future__ import annotations

import ipaddress
import json
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app import __version__
from app.config import EDITABLE_SETTING_KEYS, EditableScannerParameters, get_settings
from app.database import utc_iso
from app.logging_config import configure_logging
from app.models import FeeQuote, FeeStatus, OrderBook
from app.runtime import ScannerRuntime
from app.services.book_analytics import analyze_book
from app.services.csv_export import OPPORTUNITY_CSV_FIELDS, PAPER_CSV_FIELDS, csv_chunks
from app.services.depth_calculator import calculate_depth
from app.services.llm_config import ConfigurationFailure, LLMConfigStore, LLMConfiguration, validate_public_endpoint
from app.services.market_discovery import normalize_market, parse_bool, parse_list
from app.services.quote_freshness import UNKNOWN_QUOTE_AGE, oldest_quote_age, quote_age_seconds
from app.services.translation import DeepSeekTranslator, TranslationService, deepseek_api_base, deepseek_key

DEFAULT_INSPECT_QUANTITY = Decimal("100")
DEFAULT_INSPECT_COST = Decimal("0.05")
LLM_CONFIG_PATH = Path("data/llm-config.json")
settings = get_settings()
configure_logging(settings.log_level)
templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    runtime = ScannerRuntime(settings)
    application.state.runtime = runtime
    translations: TranslationService | None = None
    try:
        await runtime.start()
        configuration = LLMConfigStore(LLM_CONFIG_PATH, env_key=deepseek_key, env_base=deepseek_api_base)
        application.state.llm_config = configuration
        translations = TranslationService(
            Path("data/translations.sqlite3"), configured_translator(configuration.current)
        )
        application.state.translations = translations
        await translations.start()
        yield
    finally:
        try:
            if translations is not None:
                await translations.close()
        finally:
            await runtime.stop()


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


class PaperTradeRequest(BaseModel):
    market_id: str = Field(min_length=1, max_length=64)


class TranslationRequest(BaseModel):
    texts: list[Annotated[str, Field(min_length=1, max_length=20000)]] = Field(min_length=1, max_length=80)

    @field_validator("texts")
    @classmethod
    def bounded_text(cls, values: list[str]) -> list[str]:
        if sum(len(x) for x in values) > 100000:
            raise ValueError("本次翻译文本过长, 请分批提交")
        return values


class SettingsUpdate(EditableScannerParameters):
    pass


def runtime(request: Request) -> ScannerRuntime:
    return request.app.state.runtime


def configured_translator(configuration: LLMConfiguration) -> DeepSeekTranslator:
    return DeepSeekTranslator(
        configuration.api_key,
        api_base=configuration.api_base,
        provider=configuration.provider,
        model=configuration.model,
        revision=configuration.revision,
    )


def local_configuration_request(request: Request, *, mutation: bool = True) -> None:
    """Credential configuration belongs to the local origin, including on a LAN-bound scanner."""
    host = request.url.hostname or ""
    try:
        host_is_local = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        host_is_local = False
    try:
        client_is_local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        client_is_local = False
    if mutation and (not host_is_local or not client_is_local):
        raise HTTPException(403, "API configuration is available only from the local computer.")
    if request.headers.get("sec-fetch-site", "none") not in {"none", "same-origin"}:
        raise HTTPException(403, "API configuration requires a request from this website's origin.")
    if origin := request.headers.get("origin"):
        try:
            parsed = urlsplit(origin)
            valid_origin = parsed.scheme == request.url.scheme and parsed.netloc == request.url.netloc
        except ValueError:
            valid_origin = False
        if not valid_origin:
            raise HTTPException(403, "API configuration requires a request from this website's origin.")


def public_configuration_response(configuration: LLMConfiguration) -> JSONResponse:
    return JSONResponse(configuration.public(), headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@app.get("/api/llm/config")
def get_llm_configuration(request: Request) -> JSONResponse:
    # Metadata contains no key. This also supports the loopback port published by Docker,
    # whose container sees the host bridge's address rather than a loopback client address.
    local_configuration_request(request, mutation=False)
    store: LLMConfigStore | None = getattr(request.app.state, "llm_config", None)
    if store is not None:
        return public_configuration_response(store.current)
    provider = request.app.state.translations.provider
    # Isolated manual fixture servers intentionally replace the application's lifespan.
    return public_configuration_response(
        LLMConfiguration(
            provider=provider.provider,
            api_base=provider.api_base,
            model=provider.model,
            api_key=provider.api_key,
            revision=provider.revision,
        )
    )


@app.put("/api/llm/config")
async def update_llm_configuration(request: Request) -> JSONResponse:
    local_configuration_request(request)
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise HTTPException(415, "Send API configuration as JSON.")
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > 8192:
            raise HTTPException(413, "The API configuration request is too large.")
    try:
        body = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "The API configuration JSON is invalid.") from None
    store: LLMConfigStore | None = getattr(request.app.state, "llm_config", None)
    if store is None:
        raise HTTPException(503, "API configuration is unavailable in this test server.")
    async with store.lock:
        try:
            configuration = store.prepare(body, previous=store.current)
            await validate_public_endpoint(configuration.provider, configuration.api_base)
            store.save(configuration)
        except ConfigurationFailure as exc:
            raise HTTPException(422, str(exc)) from None
        await request.app.state.translations.reconfigure(configured_translator(configuration))
        store.current = configuration
    return public_configuration_response(store.current)


@app.delete("/api/llm/config")
async def remove_llm_configuration(request: Request) -> JSONResponse:
    local_configuration_request(request)
    store: LLMConfigStore | None = getattr(request.app.state, "llm_config", None)
    if store is None:
        raise HTTPException(503, "API configuration is unavailable in this test server.")
    async with store.lock:
        try:
            configuration = store.remove()
        except ConfigurationFailure as exc:
            raise HTTPException(422, str(exc)) from None
        await request.app.state.translations.reconfigure(configured_translator(configuration))
        store.current = configuration
    return public_configuration_response(store.current)


def register_translation_text(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    request.app.state.translations.register(payload)
    return payload


def book_analysis(book: OrderBook | None, max_age: Decimal, *, now: datetime | None = None) -> dict[str, Any] | None:
    if book is None:
        return None
    analysis: dict[str, Any] = analyze_book(book)
    age = quote_age_seconds(book.timestamp, now=now)
    analysis["quote_age_seconds"] = str(age) if age is not None else None
    analysis["stale"] = age is None or age > max_age
    return analysis


@app.post("/api/translations")
async def translate_public_text(body: TranslationRequest, request: Request) -> dict[str, Any]:
    return request.app.state.translations.resolve(body.texts)


@app.get("/health")
def health(request: Request) -> JSONResponse:
    rt = runtime(request)
    healthy = rt.database.health()
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "version": __version__, "mode": "public-read-only"},
        status_code=200 if healthy else 503,
    )


@app.get("/api/system/status")
async def system_status(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    status = rt.status.model_dump(mode="json")
    status["websocket_status"] = "已连接" if rt.websocket.connected else "未连接"
    status["websocket_errors"] = rt.websocket.errors
    status["websocket_reconnects"] = rt.websocket.reconnects
    status.update({"database": "正常" if rt.database.health() else "异常", "version": __version__, "read_only": True})
    status["public_http"] = rt.http.metrics()
    status["live_scanner_enabled"] = rt.settings.enable_live_scanner
    status["scanner_selection"] = dict(rt.catalog.snapshot.scanner_selection)
    status["opportunity_count"] = sum(
        rt.valid_opportunity(rt.markets[mid], result) for mid, result in rt.results.items() if mid in rt.markets
    )
    return status


@app.get("/api/dashboard")
async def dashboard_api(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    return {
        "status": await system_status(request),
        "paper_trade_count": rt.database.paper_trade_count(),
        "estimated_paper_profit": str(rt.database.paper_profit_total()),
        "read_only": True,
    }


@app.get("/api/markets")
async def markets_api(
    request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
) -> dict[str, Any]:
    rt = runtime(request)
    items = list(rt.markets.values())
    return register_translation_text(
        request, {"total": len(items), "items": [rt.market_payload(item) for item in items[offset : offset + limit]]}
    )


@app.get("/api/markets/{market_id}")
async def market_api(market_id: str, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    market = rt.markets.get(market_id)
    if market is None:
        raise HTTPException(404, "市场不存在或尚未加载")
    payload = rt.market_payload(market)
    yes_book = rt.books.get(market.yes_token_id)
    no_book = rt.books.get(market.no_token_id)
    payload["yes_orderbook"] = yes_book.model_dump(mode="json") if yes_book else None
    payload["no_orderbook"] = no_book.model_dump(mode="json") if no_book else None
    payload["book_analytics"] = [
        book_analysis(book, Decimal(rt.settings.max_quote_age_seconds)) for book in (yes_book, no_book)
    ]
    payload["calculation_orderbooks"] = [
        rt.calculation_books[token].model_dump(mode="json") if token in rt.calculation_books else None
        for token in (market.yes_token_id, market.no_token_id)
    ]
    payload["calculation_as_of"] = (
        rt.status.last_orderbook_refresh.isoformat() if rt.status.last_orderbook_refresh else None
    )
    payload["display_orderbooks_source"] = "公开 REST / Market WebSocket 展示快照"
    return register_translation_text(request, payload)


@app.get("/api/opportunities")
async def opportunities_api(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    items = []
    for market_id, result in rt.results.items():
        if market_id in rt.markets and rt.valid_opportunity(rt.markets[market_id], result):
            items.append(
                {"market": rt.market_payload(rt.markets[market_id]), "calculation": result.model_dump(mode="json")}
            )
    return register_translation_text(request, {"total": len(items), "items": items})


@app.get("/api/opportunities/history")
def opportunities_history(
    request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
) -> dict[str, Any]:
    items = runtime(request).database.list_opportunities(limit, offset)
    return register_translation_text(request, {"items": items, "limit": limit, "offset": offset})


@app.post("/api/paper-trades")
async def create_paper_trade(body: PaperTradeRequest, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    try:
        trade_id = await rt.create_paper_trade(body.market_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"id": trade_id, "status": "SUCCESS", "simulation_only": True}


@app.get("/api/paper-trades")
def paper_trades_api(
    request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
) -> dict[str, Any]:
    return register_translation_text(
        request, {"items": runtime(request).database.list_paper_trades(limit, offset), "limit": limit, "offset": offset}
    )


@app.get("/api/paper-trades/{trade_id}")
def paper_trade_details(trade_id: int, request: Request) -> dict[str, Any]:
    payload = runtime(request).database.get_paper_trade_details(trade_id)
    if payload is None:
        raise HTTPException(404, "模拟记录不存在")
    return register_translation_text(request, payload)


@app.get("/api/opportunities/history/{opportunity_id}")
def opportunity_details(opportunity_id: int, request: Request) -> dict[str, Any]:
    payload = runtime(request).database.get_opportunity_details(opportunity_id)
    if payload is None:
        raise HTTPException(404, "历史信号不存在")
    return register_translation_text(request, payload)


@app.get("/api/settings")
def get_application_settings(request: Request) -> dict[str, str]:
    rt = runtime(request)
    return {key: str(getattr(rt.settings, key)) for key in EDITABLE_SETTING_KEYS}


@app.put("/api/settings")
async def update_application_settings(body: SettingsUpdate, request: Request) -> dict[str, str]:
    rt = runtime(request)
    await rt.apply_parameters({key: str(value) for key, value in body.model_dump().items()})
    return get_application_settings(request)


@app.get("/api/logs")
def logs_api(request: Request, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    rows = runtime(request).database.list_events(limit)
    return {
        "items": [
            {
                "id": row.id,
                "created_at": utc_iso(row.created_at),
                "level": row.level,
                "source": row.source,
                "event": row.event,
                "message": row.message,
            }
            for row in rows
        ]
    }


def _csv_response(rows: Iterable[dict[str, Any]], filename: str, fields: list[str]) -> StreamingResponse:
    return StreamingResponse(
        csv_chunks(rows, fields),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/exports/opportunities.csv")
def export_opportunities(request: Request) -> StreamingResponse:
    return _csv_response(runtime(request).database.iter_opportunities(), "opportunities.csv", OPPORTUNITY_CSV_FIELDS)


@app.get("/api/exports/paper-trades.csv")
def export_paper_trades(request: Request) -> StreamingResponse:
    return _csv_response(runtime(request).database.iter_paper_trades(), "paper-trades.csv", PAPER_CSV_FIELDS)


@app.get("/monitor", response_class=HTMLResponse)
def monitor_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"page": "dashboard"})


@app.get("/opportunities", response_class=HTMLResponse)
def opportunities_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="opportunities.html", context={"page": "opportunities"})


@app.get("/markets/{market_id}", response_class=HTMLResponse)
def market_page(market_id: str, request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name="market_detail.html", context={"page": "market", "market_id": market_id}
    )


@app.get("/paper-trades", response_class=HTMLResponse)
def paper_trades_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="paper_trades.html", context={"page": "paper-trades"})


@app.get("/history", response_class=HTMLResponse)
def history_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="history.html", context={"page": "history"})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="settings.html", context={"page": "settings"})


@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="logs.html", context={"page": "logs"})


@app.get("/", response_class=HTMLResponse)
def research_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="research.html", context={"page": "research"})


@app.get("/api/research")
def research_data() -> dict[str, Any]:
    return json.loads(Path("app/research.json").read_text(encoding="utf-8"))


@app.get("/api/catalog")
async def catalog_api(
    request: Request,
    category: Literal["all", "sports", "weather", "crypto", "economy", "politics", "other"] = "all",
    search: str = Query("", max_length=500),
    sort: Literal["volume24h", "liquidity", "newest", "ending"] = "volume24h",
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_liquidity: float = Query(0, ge=0, allow_inf_nan=False),
) -> dict[str, Any]:
    rt = runtime(request)
    snapshot = rt.catalog.snapshot
    rows = [
        x
        for x in snapshot.items.values()
        if (category == "all" or x["category"] == category)
        and (not search or search.casefold() in (x["question"] + " " + x["event"]).casefold())
        and x["liquidity"] >= min_liquidity
    ]
    if sort == "newest":
        rows.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
    elif sort == "ending":
        rows.sort(key=lambda x: x.get("endDate") or "9999")
    else:
        rows.sort(key=lambda x: x["liquidity"] if sort == "liquidity" else x["volume24h"], reverse=True)
    result = rt.catalog.summary(snapshot)
    result.update(
        {
            "filteredTotal": len(rows),
            "items": rows[offset : offset + limit],
            "filteredVolume24h": sum(x["volume24h"] for x in rows),
            "filteredLiquidity": sum(x["liquidity"] for x in rows),
            "offset": offset,
            "limit": limit,
            "scannerCount": len(rt.markets),
            "liveScannerEnabled": rt.settings.enable_live_scanner,
            "scannerRefreshSeconds": rt.settings.rest_refresh_seconds,
            "candidateCount": sum(
                rt.valid_opportunity(rt.markets[mid], c) for mid, c in rt.results.items() if mid in rt.markets
            ),
        }
    )
    return register_translation_text(request, result)


@app.get("/api/inspect/{market_id}")
async def inspect_market(
    market_id: str,
    request: Request,
    quantity: Annotated[Decimal, Query(ge=1, le=100000)] = DEFAULT_INSPECT_QUANTITY,
    extra_cost: Annotated[Decimal, Query(ge=0, le=10000)] = DEFAULT_INSPECT_COST,
) -> dict[str, Any]:
    rt = runtime(request)
    snapshot = rt.catalog.snapshot
    item = snapshot.items.get(market_id)
    raw = snapshot.raw.get(market_id)
    if item is None or raw is None:
        raise HTTPException(404, "市场尚未进入目录")
    result = dict(item)
    try:
        # Catalog browsing tolerates older metadata; a cost decision needs the
        # latest API response and exact original outcome/token mapping. Gamma
        # may cache metadata; observed_at is our receipt time, not source time.
        latest_rows = await rt.gamma.fetch_markets_by_ids([market_id])
        observed_at = datetime.now(UTC)
        result["metadataAsOf"] = observed_at.isoformat()
        current = latest_rows[0] if latest_rows else None
        reason = ""
        if current is None:
            reason = "本次公开接口未返回该开盘市场; 可能已关闭, 暂停成本核验"
        elif (
            not parse_bool(current.get("active"))
            or parse_bool(current.get("closed"), default=True)
            or not parse_bool(current.get("acceptingOrders", current.get("accepting_orders")))
            or not parse_bool(current.get("enableOrderBook", current.get("enable_order_book")))
        ):
            reason = "市场已关闭或停止接受交易, 暂停成本核验"
        elif (
            parse_list(current.get("clobTokenIds", current.get("clob_token_ids"))) != item["tokens"]
            or parse_list(current.get("outcomes")) != item["outcomes"]
            or not isinstance(current.get("conditionId", current.get("condition_id")), str)
            or current.get("conditionId", current.get("condition_id"))
            != raw.get("conditionId", raw.get("condition_id"))
        ):
            reason = "市场标识或结果与 Token 映射已变化, 等待目录更新后核验"
        if reason:
            result.update(
                available=False,
                unavailableReason=reason,
                books=[None for _ in item["tokens"]],
                book_analytics=[None for _ in item["tokens"]],
                calculation=None,
                asOf=observed_at.isoformat(),
            )
            return register_translation_text(request, result)
        assert current is not None
        raw = current
        result.update(
            available=True,
            question=current.get("question", item["question"]),
            description=current.get("description", item.get("description", "")),
        )
        books = await rt.clob.fetch_books(item["tokens"])
        observed_at = datetime.now(UTC)
        as_of = observed_at.isoformat()
        result.update(
            {
                "books": [books[t].model_dump(mode="json") if t in books else None for t in item["tokens"]],
                "book_analytics": [
                    book_analysis(books.get(t), Decimal(rt.settings.max_quote_age_seconds), now=observed_at)
                    for t in item["tokens"]
                ],
                "asOf": as_of,
                "calculation": None,
            }
        )
        if (
            len(item["tokens"]) == 2
            and len(set(item["tokens"])) == 2
            and len(item["outcomes"]) == 2
            and len(set(item["outcomes"])) == 2
            and all(t in books for t in item["tokens"])
        ):
            # The two labels can be teams or Up/Down. Preserve label-token order for display.
            copy = dict(raw)
            copy["outcomes"] = ["Yes", "No"]
            market = normalize_market(copy)
            if market.fees_enabled is False:
                fee = FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=Decimal("0"))
            elif market.fee_rate is not None:
                fee = FeeQuote(status=FeeStatus.KNOWN, base_fee_bps=market.fee_rate * Decimal("1000"))
            else:
                fee = FeeQuote(status=FeeStatus.UNKNOWN, reason="市场费率或费率公式未核实")
            calc = calculate_depth(
                books[item["tokens"][0]],
                books[item["tokens"][1]],
                quantity,
                fee,
                slippage_rate=Decimal(rt.settings.slippage_rate),
                safety_rate=Decimal(rt.settings.safety_rate),
                extra_cost=extra_cost,
                expected_condition_id=market.condition_id,
            )
            relevant_books = [books[token] for token in item["tokens"]]
            minimum = (
                max(book.min_order_size for book in relevant_books if book.min_order_size is not None)
                if all(book.min_order_size is not None for book in relevant_books)
                else None
            )
            age = oldest_quote_age((book.timestamp for book in relevant_books), now=observed_at)
            calc.quote_age = age if age is not None else UNKNOWN_QUOTE_AGE
            if calc.status in {"VALID", "PARTIAL", "FEE_UNKNOWN"} and (
                age is None or calc.quote_age > Decimal(rt.settings.max_quote_age_seconds)
            ):
                calc.status = "STALE"
            elif calc.status in {"VALID", "PARTIAL"}:
                if minimum is None:
                    calc.status = "MIN_ORDER_UNKNOWN"
                elif calc.executable_quantity < minimum:
                    calc.status = "BELOW_MIN_ORDER"
            result["calculation"] = calc.model_dump(mode="json")
            result["minimumOrderSize"] = str(minimum) if minimum is not None else None
        return register_translation_text(request, result)
    except Exception as exc:
        raise HTTPException(502, "公开盘口暂时无法读取; 请稍后重试") from exc
