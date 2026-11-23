
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from quant_alpha.data.schema import OrderBookSnapshot
from quant_alpha.features.market_depth.orderbook import OrderBookEngine


def valid_snapshot():
    timestamp = datetime(
        2026, 11, 23, 10, 30,
        tzinfo=ZoneInfo("Asia/Kolkata"),
    )

    return OrderBookSnapshot(
        instrument_id="NSE_NIFTY_FUT",
        symbol="NIFTY",
        exchange="NSE",
        provider="TEST",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        sequence_number=1001,
        bids=[
            {"price": 26000.0, "quantity": 500},
            {"price": 25999.0, "quantity": 300},
            {"price": 25998.0, "quantity": 200},
        ],
        asks=[
            {"price": 26001.0, "quantity": 200},
            {"price": 26002.0, "quantity": 250},
            {"price": 26003.0, "quantity": 150},
        ],
    )


def test_load_snapshot():
    engine = OrderBookEngine("NSE_NIFTY_FUT")
    engine.load_snapshot(valid_snapshot())

    assert engine.is_initialized


def test_best_bid_and_ask():
    engine = OrderBookEngine("NSE_NIFTY_FUT")
    engine.load_snapshot(valid_snapshot())

    assert engine.best_bid.price == 26000.0
    assert engine.best_ask.price == 26001.0


def test_spread():
    engine = OrderBookEngine("NSE_NIFTY_FUT")
    engine.load_snapshot(valid_snapshot())

    assert engine.spread == 1.0


def test_mid_price():
    engine = OrderBookEngine("NSE_NIFTY_FUT")
    engine.load_snapshot(valid_snapshot())

    assert engine.mid_price == 26000.5


def test_depth_imbalance():
    engine = OrderBookEngine("NSE_NIFTY_FUT")
    engine.load_snapshot(valid_snapshot())

    assert engine.depth_imbalance(3) == pytest.approx(0.25)


def test_invalid_instrument():
    engine = OrderBookEngine("NSE_BANKNIFTY_FUT")

    with pytest.raises(ValueError):
        engine.load_snapshot(valid_snapshot())


def test_uninitialized_order_book():
    engine = OrderBookEngine("NSE_NIFTY_FUT")

    with pytest.raises(RuntimeError):
        _ = engine.best_bid


def test_invalid_depth():
    engine = OrderBookEngine("NSE_NIFTY_FUT")
    engine.load_snapshot(valid_snapshot())

    with pytest.raises(ValueError):
        engine.depth_imbalance(0)
