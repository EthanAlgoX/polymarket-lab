from __future__ import annotations

from decimal import Decimal

from app.services.orderbooks import normalize_orderbook


def test_orderbook_sorts_and_merges_levels() -> None:
    book = normalize_orderbook(
        {
            "asset_id": "t",
            "bids": [{"price": "0.2", "size": "1"}, {"price": "0.4", "size": "2"}],
            "asks": [{"price": "0.7", "size": "1"}, {"price": "0.6", "size": "2"}, {"price": "0.6", "size": "3"}],
        }
    )
    assert [x.price for x in book.bids] == [Decimal("0.4"), Decimal("0.2")]
    assert [x.price for x in book.asks] == [Decimal("0.6"), Decimal("0.7")]
    assert book.asks[0].size == Decimal("5")
    assert book.best_bid == Decimal("0.4")
    assert book.best_ask == Decimal("0.6")


def test_invalid_levels_are_removed() -> None:
    book = normalize_orderbook(
        {
            "asset_id": "t",
            "asks": [
                {"price": "-1", "size": "1"},
                {"price": "NaN", "size": "1"},
                {"price": "0.5", "size": "-2"},
                {"price": "0.4", "size": "2"},
            ],
        }
    )
    assert len(book.asks) == 1
    assert book.asks[0].price == Decimal("0.4")


def test_empty_orderbook() -> None:
    book = normalize_orderbook({"asset_id": "t", "bids": [], "asks": []})
    assert book.best_bid is None
    assert book.best_ask is None


def test_optional_metadata() -> None:
    book = normalize_orderbook({"asset_id": "t", "tick_size": "0.001", "last_trade_price": "0.33"})
    assert book.tick_size == Decimal("0.001")
    assert book.last_trade_price == Decimal("0.33")
