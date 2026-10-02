from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app import __version__
from app.config import get_settings
from app.logging_config import configure_logging
from app.models import FeeQuote, FeeStatus, OrderBook
from app.runtime import ScannerRuntime
from app.services.book_analytics import analyze_book
from app.services.depth_calculator import calculate_depth
from app.services.market_discovery import normalize_market
from app.services.quote_freshness import UNKNOWN_QUOTE_AGE, oldest_quote_age, quote_age_seconds
from app.services.translation import DeepSeekTranslator, TranslationService, deepseek_key

DEFAULT_INSPECT_QUANTITY = Decimal("100")
DEFAULT_INSPECT_COST = Decimal("0.05")
settings = get_settings()
configure_logging(settings.log_level)
templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    runtime = ScannerRuntime(settings)
    application.state.runtime = runtime
    await runtime.start()
    translations = TranslationService(Path("data/translations.sqlite3"), DeepSeekTranslator(deepseek_key()))
    application.state.translations = translations
    await translations.start()
    try:
        yield
    finally:
        await translations.close()
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


class SettingsUpdate(BaseModel):
    minimum_net_profit: Decimal = Field(ge=0, le=1000)
    minimum_net_roi: Decimal = Field(ge=0, le=1)
    default_quantity: Decimal = Field(gt=0, le=100000)
    slippage_rate: Decimal = Field(ge=0, le=0.25)
    safety_rate: Decimal = Field(ge=0, le=0.25)


def runtime(request: Request) -> ScannerRuntime:
    return request.app.state.runtime


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
def health(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    return {"status": "ok" if rt.database.health() else "degraded", "version": __version__, "mode": "public-read-only"}


@app.get("/api/system/status")
def system_status(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    status = rt.status.model_dump(mode="json")
    status["websocket_status"] = "已连接" if rt.websocket.connected else "未连接"
    status["websocket_errors"] = rt.websocket.errors
    status["websocket_reconnects"] = rt.websocket.reconnects
    status.update({"database": "正常" if rt.database.health() else "异常", "version": __version__, "read_only": True})
    status["public_http"] = rt.http.metrics()
    status["scanner_selection"] = dict(rt.catalog.snapshot.scanner_selection)
    return status


@app.get("/api/dashboard")
def dashboard_api(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    return {
        "status": rt.status.model_dump(mode="json"),
        "paper_trade_count": rt.database.paper_trade_count(),
        "estimated_paper_profit": str(rt.database.paper_profit_total()),
        "read_only": True,
    }


@app.get("/api/markets")
def markets_api(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    rt = runtime(request)
    items = list(rt.markets.values())
    return register_translation_text(
        request, {"total": len(items), "items": [rt.market_payload(item) for item in items[offset : offset + limit]]}
    )


@app.get("/api/markets/{market_id}")
def market_api(market_id: str, request: Request) -> dict[str, Any]:
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
    return register_translation_text(request, payload)


@app.get("/api/opportunities")
def opportunities_api(request: Request) -> dict[str, Any]:
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
def create_paper_trade(body: PaperTradeRequest, request: Request) -> dict[str, Any]:
    rt = runtime(request)
    market = rt.markets.get(body.market_id)
    result = rt.results.get(body.market_id)
    if market is None or result is None:
        raise HTTPException(409, "没有可追溯的实时订单簿计算结果")
    if not rt.valid_opportunity(market, result):
        raise HTTPException(409, "当前快照过期或未通过全部机会门槛; 请刷新盘口")
    trade_id = rt.database.add_paper_trade(market, result)
    return {"id": trade_id, "status": "SUCCESS" if result.status == "VALID" else "FAILED", "simulation_only": True}


@app.get("/api/paper-trades")
def paper_trades_api(
    request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
) -> dict[str, Any]:
    return register_translation_text(
        request, {"items": runtime(request).database.list_paper_trades(limit, offset), "limit": limit, "offset": offset}
    )


@app.get("/api/settings")
def get_application_settings(request: Request) -> dict[str, str]:
    rt = runtime(request)
    stored = rt.database.settings()
    return {
        "minimum_net_profit": stored.get("minimum_net_profit", settings.minimum_net_profit),
        "minimum_net_roi": stored.get("minimum_net_roi", settings.minimum_net_roi),
        "default_quantity": stored.get("default_quantity", settings.default_quantity),
        "slippage_rate": stored.get("slippage_rate", settings.slippage_rate),
        "safety_rate": stored.get("safety_rate", settings.safety_rate),
    }


@app.put("/api/settings")
def update_application_settings(body: SettingsUpdate, request: Request) -> dict[str, str]:
    rt = runtime(request)
    for key, value in body.model_dump().items():
        text = str(value)
        rt.database.upsert_setting(key, text)
        setattr(settings, key, text)
    return get_application_settings(request)


@app.get("/api/logs")
def logs_api(request: Request, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    rows = runtime(request).database.list_events(limit)
    return {
        "items": [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "level": row.level,
                "source": row.source,
                "event": row.event,
                "message": row.message,
            }
            for row in rows
        ]
    }


def _csv_response(rows: list[dict[str, Any]], filename: str) -> StreamingResponse:
    stream = io.StringIO()
    if rows:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    else:
        stream.write("status\r\n暂无数据\r\n")
    data = ("\ufeff" + stream.getvalue()).encode("utf-8")
    return StreamingResponse(
        iter([data]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/exports/opportunities.csv")
def export_opportunities(request: Request) -> StreamingResponse:
    rows = runtime(request).database.list_opportunities(5000)
    flat = [{key: value for key, value in row.items() if key != "details"} for row in rows]
    return _csv_response(flat, "opportunities.csv")


@app.get("/api/exports/paper-trades.csv")
def export_paper_trades(request: Request) -> StreamingResponse:
    return _csv_response(runtime(request).database.list_paper_trades(5000), "paper-trades.csv")


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
def catalog_api(
    request: Request,
    category: str = "all",
    search: str = "",
    sort: str = "volume24h",
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_liquidity: float = Query(0, ge=0),
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
        if len(item["tokens"]) == 2 and all(t in books for t in item["tokens"]):
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
            )
            relevant_books = [books[token] for token in item["tokens"]]
            minimum = max(book.min_order_size or Decimal("0") for book in relevant_books)
            age = oldest_quote_age((book.timestamp for book in relevant_books), now=observed_at)
            calc.quote_age = age if age is not None else UNKNOWN_QUOTE_AGE
            if age is None or calc.quote_age > Decimal(rt.settings.max_quote_age_seconds):
                calc.status = "STALE"
            elif calc.executable_quantity < minimum:
                calc.status = "BELOW_MIN_ORDER"
            result["calculation"] = calc.model_dump(mode="json")
            result["minimumOrderSize"] = str(minimum)
        return register_translation_text(request, result)
    except Exception as exc:
        raise HTTPException(502, "公开盘口暂时无法读取; 请稍后重试") from exc
