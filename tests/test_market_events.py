
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from quant_alpha.data.schema import (
    OrderBookSnapshot,
    PriceLevel,
    TradeEvent,
)


def valid_event_metadata():
    timestamp = datetime(
        2026, 11, 23, 10, 30,
        tzinfo=ZoneInfo("Asia/Kolkata"),
    )

    return {
        "instrument_id": "NSE_NIFTY_FUT",
        "symbol": "NIFTY",
        "exchange": "NSE",
        "provider": "GOCHARTING",
        "exchange_timestamp": timestamp,
        "received_timestamp": timestamp,
        "sequence_number": 1001,
    }


def test_valid_trade_event():
    data = valid_event_metadata()
    data.update({
        "price": 26000.0,
        "quantity": 50,
        "aggressor_side": "BUY",
    })

    event = TradeEvent(**data)

    assert event.price == 26000.0
    assert event.quantity == 50
    assert event.aggressor_side == "BUY"


def test_trade_event_rejects_negative_quantity():
    data = valid_event_metadata()
    data.update({
        "price": 26000.0,
        "quantity": -10,
    })

    with pytest.raises(ValidationError):
        TradeEvent(**data)


def test_trade_event_rejects_naive_timestamp():
    data = valid_event_metadata()
    data.update({
        "price": 26000.0,
        "quantity": 50,
        "exchange_timestamp": datetime(2026, 11, 23, 10, 30),
    })

    with pytest.raises(ValidationError):
        TradeEvent(**data)


def test_valid_order_book_snapshot():
    data = valid_event_metadata()
    data.update({
        "bids": [
            {"price": 26000.0, "quantity": 500},
            {"price": 25999.0, "quantity": 300},
        ],
        "asks": [
            {"price": 26001.0, "quantity": 400},
            {"price": 26002.0, "quantity": 600},
        ],
    })

    book = OrderBookSnapshot(**data)

    assert len(book.bids) == 2
    assert len(book.asks) == 2
    assert book.bids[0].price == 26000.0


def test_order_book_rejects_unsorted_bids():
    data = valid_event_metadata()
    data.update({
        "bids": [
            {"price": 25999.0, "quantity": 300},
            {"price": 26000.0, "quantity": 500},
        ],
        "asks": [
            {"price": 26001.0, "quantity": 400},
        ],
    })

    with pytest.raises(ValidationError):
        OrderBookSnapshot(**data)


def test_order_book_rejects_duplicate_bid_prices():
    data = valid_event_metadata()
    data.update({
        "bids": [
            {"price": 26000.0, "quantity": 500},
            {"price": 26000.0, "quantity": 300},
        ],
        "asks": [
            {"price": 26001.0, "quantity": 400},
        ],
    })

    with pytest.raises(ValidationError):
        OrderBookSnapshot(**data)


def test_price_level_rejects_zero_quantity():
    with pytest.raises(ValidationError):
        PriceLevel(price=26000.0, quantity=0)
