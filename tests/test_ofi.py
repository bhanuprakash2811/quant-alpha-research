
from datetime import UTC, datetime, timedelta

import pytest

from quant_alpha.data.schema import OrderBookSnapshot, PriceLevel
from quant_alpha.features.orderflow.ofi import (
    OrderFlowImbalanceCalculator,
)


def create_snapshot(
    timestamp: datetime,
    bid_price: float = 26000,
    bid_quantity: int = 500,
    ask_price: float = 26001,
    ask_quantity: int = 400,
    instrument_id: str = "NIFTY-FUT",
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        instrument_id=instrument_id,
        symbol="NIFTY",
        exchange="NSE",
        provider="test",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        bids=[PriceLevel(price=bid_price, quantity=bid_quantity)],
        asks=[PriceLevel(price=ask_price, quantity=ask_quantity)],
    )


@pytest.fixture
def timestamps():
    previous = datetime(2026, 11, 23, 9, 15, tzinfo=UTC)
    current = previous + timedelta(seconds=1)
    return previous, current


def test_bid_quantity_increase_produces_positive_ofi(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(previous_time, bid_quantity=500)
    current = create_snapshot(current_time, bid_quantity=700)

    result = OrderFlowImbalanceCalculator.calculate(previous, current)

    assert result.bid_component == 200
    assert result.value == 200


def test_bid_price_increase_produces_positive_ofi(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(previous_time, bid_price=26000)
    current = create_snapshot(current_time, bid_price=26001)

    result = OrderFlowImbalanceCalculator.calculate(previous, current)

    assert result.bid_component == 500


def test_bid_price_decrease_produces_negative_ofi(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(previous_time, bid_price=26000)
    current = create_snapshot(current_time, bid_price=25999)

    result = OrderFlowImbalanceCalculator.calculate(previous, current)

    assert result.bid_component == -500


def test_ask_quantity_increase_produces_negative_ofi(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(previous_time, ask_quantity=400)
    current = create_snapshot(current_time, ask_quantity=600)

    result = OrderFlowImbalanceCalculator.calculate(previous, current)

    assert result.ask_component == -200


def test_ask_price_decrease_produces_negative_ofi(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(previous_time, ask_price=26001)
    current = create_snapshot(current_time, ask_price=26000)

    result = OrderFlowImbalanceCalculator.calculate(previous, current)

    assert result.ask_component == -400


def test_ask_price_increase_produces_positive_ofi(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(previous_time, ask_price=26001)
    current = create_snapshot(current_time, ask_price=26002)

    result = OrderFlowImbalanceCalculator.calculate(previous, current)

    assert result.ask_component == 400


def test_unchanged_order_book_produces_zero_ofi(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(previous_time)
    current = create_snapshot(current_time)

    result = OrderFlowImbalanceCalculator.calculate(previous, current)

    assert result.value == 0


def test_wrong_instrument_is_rejected(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(previous_time)
    current = create_snapshot(
        current_time,
        instrument_id="BANKNIFTY-FUT",
    )

    with pytest.raises(ValueError, match="same instrument"):
        OrderFlowImbalanceCalculator.calculate(previous, current)


def test_non_increasing_timestamp_is_rejected(timestamps):
    previous_time, current_time = timestamps

    previous = create_snapshot(current_time)
    current = create_snapshot(previous_time)

    with pytest.raises(ValueError, match="later timestamp"):
        OrderFlowImbalanceCalculator.calculate(previous, current)
