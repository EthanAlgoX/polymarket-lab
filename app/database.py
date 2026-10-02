from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class MarketRow(Base):
    __tablename__ = "markets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    condition_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    event_id: Mapped[str] = mapped_column(String(64), default="")
    question: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    accepting_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    liquidity: Mapped[str] = mapped_column(String(64), default="0")
    volume: Mapped[str] = mapped_column(String(64), default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    tokens: Mapped[list[MarketTokenRow]] = relationship(back_populates="market", cascade="all, delete-orphan")


class MarketTokenRow(Base):
    __tablename__ = "market_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    outcome: Mapped[str] = mapped_column(String(20))
    outcome_index: Mapped[int] = mapped_column(Integer)
    token_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    market: Mapped[MarketRow] = relationship(back_populates="tokens")


class OrderbookSnapshotRow(Base):
    __tablename__ = "orderbook_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[str] = mapped_column(String(64), index=True)
    token_id: Mapped[str] = mapped_column(String(128), index=True)
    book_hash: Mapped[str] = mapped_column(String(128), default="")
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class OpportunityRow(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    market_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    initial_net_profit: Mapped[str] = mapped_column(String(64))
    max_net_profit: Mapped[str] = mapped_column(String(64))
    min_net_profit: Mapped[str] = mapped_column(String(64))
    max_net_roi: Mapped[str] = mapped_column(String(64))
    max_quantity: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    disappeared_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaperTradeRow(Base):
    __tablename__ = "paper_trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    market_id: Mapped[str] = mapped_column(String(64), index=True)
    market_question: Mapped[str] = mapped_column(Text)
    target_quantity: Mapped[str] = mapped_column(String(64))
    executable_quantity: Mapped[str] = mapped_column(String(64))
    total_cost: Mapped[str] = mapped_column(String(64))
    net_profit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    net_roi: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(40))
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual")
    data_source: Mapped[str] = mapped_column(String(60), default="Polymarket public CLOB")
    payload_json: Mapped[str] = mapped_column(Text)


class DailyStatisticRow(Base):
    __tablename__ = "daily_statistics"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10), unique=True)
    opportunities: Mapped[int] = mapped_column(Integer, default=0)
    paper_trades: Mapped[int] = mapped_column(Integer, default=0)
    estimated_profit: Mapped[str] = mapped_column(String(64), default="0")


class SystemEventRow(Base):
    __tablename__ = "system_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    level: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    event: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    market_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ApplicationSettingRow(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


Index("ix_opportunities_status_last_seen", OpportunityRow.status, OpportunityRow.last_seen)


class Database:
    def __init__(self, url: str) -> None:
        engine_options: dict[str, Any] = {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
        if url == "sqlite:///:memory:":
            engine_options["poolclass"] = StaticPool
        self.engine = create_engine(url, **engine_options)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._sqlite_pragmas)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _sqlite_pragmas(connection: Any, _: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def session(self) -> Iterator[Session]:
        with self.Session.begin() as session:
            yield session

    def health(self) -> bool:
        with self.Session() as session:
            return session.scalar(select(func.count()).select_from(ApplicationSettingRow)) is not None

    def add_event(self, level: str, source: str, event_name: str, message: str, market_id: str | None = None) -> None:
        with self.Session.begin() as session:
            session.add(
                SystemEventRow(level=level, source=source, event=event_name, message=message[:500], market_id=market_id)
            )

    def upsert_setting(self, key: str, value: str) -> None:
        with self.Session.begin() as session:
            row = session.get(ApplicationSettingRow, key)
            if row is None:
                session.add(ApplicationSettingRow(key=key, value=value))
            else:
                row.value = value
                row.updated_at = datetime.now(UTC)

    def settings(self) -> dict[str, str]:
        with self.Session() as session:
            return {row.key: row.value for row in session.scalars(select(ApplicationSettingRow)).all()}

    def list_events(self, limit: int = 100) -> list[SystemEventRow]:
        with self.Session() as session:
            return list(session.scalars(select(SystemEventRow).order_by(SystemEventRow.id.desc()).limit(limit)).all())

    def paper_trade_count(self) -> int:
        with self.Session() as session:
            return int(session.scalar(select(func.count()).select_from(PaperTradeRow)) or 0)

    def paper_profit_total(self) -> Decimal:
        with self.Session() as session:
            values = session.scalars(
                select(PaperTradeRow.net_profit).where(PaperTradeRow.net_profit.is_not(None))
            ).all()
            return sum((Decimal(value) for value in values if value is not None), Decimal("0"))

    def upsert_market(self, market: Any) -> None:
        with self.Session.begin() as session:
            row = session.get(MarketRow, market.market_id)
            if row is None:
                row = MarketRow(
                    id=market.market_id,
                    condition_id=market.condition_id,
                    event_id=market.event_id,
                    question=market.question,
                )
                session.add(row)
            row.slug = market.slug
            row.category = market.category
            row.active = market.active
            row.closed = market.closed
            row.accepting_orders = market.accepting_orders
            row.liquidity = str(market.liquidity)
            row.volume = str(market.volume)
            row.updated_at = datetime.now(UTC)
            existing = {token.outcome: token for token in row.tokens}
            for index, (outcome, token_id) in enumerate(zip(market.outcomes, market.token_ids, strict=True)):
                token = existing.get(outcome)
                if token is None:
                    row.tokens.append(MarketTokenRow(outcome=outcome, outcome_index=index, token_id=token_id))
                else:
                    token.outcome_index = index
                    token.token_id = token_id

    def upsert_opportunity(self, market: Any, result: Any) -> None:
        now = datetime.now(UTC)
        profit = str(result.net_profit or Decimal("0"))
        roi = str(result.net_roi or Decimal("0"))
        with self.Session.begin() as session:
            row = session.scalar(
                select(OpportunityRow).where(OpportunityRow.fingerprint == result.snapshot_fingerprint)
            )
            if row is None:
                session.add(
                    OpportunityRow(
                        fingerprint=result.snapshot_fingerprint,
                        market_id=market.market_id,
                        question=market.question,
                        initial_net_profit=profit,
                        max_net_profit=profit,
                        min_net_profit=profit,
                        max_net_roi=roi,
                        max_quantity=str(result.executable_quantity),
                        payload_json=result.model_dump_json(),
                    )
                )
            else:
                row.last_seen = now
                row.max_net_profit = str(max(Decimal(row.max_net_profit), Decimal(profit)))
                row.min_net_profit = str(min(Decimal(row.min_net_profit), Decimal(profit)))
                row.max_net_roi = str(max(Decimal(row.max_net_roi), Decimal(roi)))
                row.max_quantity = str(max(Decimal(row.max_quantity), result.executable_quantity))
                row.payload_json = result.model_dump_json()

    def add_paper_trade(self, market: Any, result: Any, trigger_type: str = "manual") -> int:
        status = "SUCCESS" if result.status == "VALID" else "FAILED"
        with self.Session.begin() as session:
            row = PaperTradeRow(
                market_id=market.market_id,
                market_question=market.question,
                target_quantity=str(result.target_quantity),
                executable_quantity=str(result.executable_quantity),
                total_cost=str(result.total_cost),
                net_profit=str(result.net_profit) if result.net_profit is not None else None,
                net_roi=str(result.net_roi) if result.net_roi is not None else None,
                status=status,
                failure_reason=None if status == "SUCCESS" else result.status,
                trigger_type=trigger_type,
                payload_json=result.model_dump_json(),
            )
            session.add(row)
            session.flush()
            return row.id

    def list_paper_trades(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self.Session() as session:
            rows = session.scalars(
                select(PaperTradeRow).order_by(PaperTradeRow.id.desc()).offset(offset).limit(limit)
            ).all()
            return [
                {
                    "id": row.id,
                    "created_at": row.created_at.isoformat(),
                    "market_id": row.market_id,
                    "market_question": row.market_question,
                    "target_quantity": row.target_quantity,
                    "executable_quantity": row.executable_quantity,
                    "total_cost": row.total_cost,
                    "net_profit": row.net_profit,
                    "net_roi": row.net_roi,
                    "status": row.status,
                    "failure_reason": row.failure_reason,
                    "trigger_type": row.trigger_type,
                    "data_source": row.data_source,
                }
                for row in rows
            ]

    def list_opportunities(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self.Session() as session:
            rows = session.scalars(
                select(OpportunityRow).order_by(OpportunityRow.last_seen.desc()).offset(offset).limit(limit)
            ).all()
            return [
                {
                    "id": row.id,
                    "market_id": row.market_id,
                    "question": row.question,
                    "first_seen": row.first_seen.isoformat(),
                    "last_seen": row.last_seen.isoformat(),
                    "status": row.status,
                    "max_net_profit": row.max_net_profit,
                    "max_net_roi": row.max_net_roi,
                    "max_quantity": row.max_quantity,
                    "disappeared_reason": row.disappeared_reason,
                    "details": json.loads(row.payload_json),
                }
                for row in rows
            ]
