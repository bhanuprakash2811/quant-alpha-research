
from datetime import UTC, datetime

import pytest

from quant_alpha.data.schema import OrderBookSnapshot, PriceLevel
from quant_alpha.features.microstructure.engine import (
    MicrostructureEngine,
)


@pytest.fixture
def order_book():
    timestamp = datetime(2026, 11, 23, 9, 15, tzinfo=UTC)

    return OrderBookSnapshot(
        instrument_id="NIFTY-FUT",
        symbol="NIFTY",
        exchange="NSE",
        provider="test",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        bids=[
            PriceLevel(price=26000, quantity=500),
            PriceLevel(price=25999, quantity=300),
            PriceLevel(price=25998, quantity=200),
        ],
        asks=[
            PriceLevel(price=26001, quantity=200),
            PriceLevel(price=26002, quantity=250),
            PriceLevel(price=26003, quantity=150),
        ],
    )


def test_mid_price(order_book):
    result = MicrostructureEngine.calculate(order_book)

    assert result.mid_price == pytest.approx(26000.5)


def test_microprice(order_book):
    result = MicrostructureEngine.calculate(order_book)

    expected = (
        26001 * 500 + 26000 * 200
    ) / 700

    assert result.microprice == pytest.approx(expected)


def test_spread(order_book):
    result = MicrostructureEngine.calculate(order_book)

    assert result.spread == pytest.approx(1)


def test_spread_in_basis_points(order_book):
    result = MicrostructureEngine.calculate(order_book)

    expected = (1 / 26000.5) * 10000

    assert result.spread_bps == pytest.approx(expected)


def test_depth_imbalance(order_book):
    result = MicrostructureEngine.calculate(order_book)

    expected = (1000 - 600) / (1000 + 600)

    assert result.depth_imbalance == pytest.approx(expected)


def test_weighted_depth_imbalance(order_book):
    result = MicrostructureEngine.calculate(order_book)

    weighted_bid = 500 + 300 / 2 + 200 / 3
    weighted_ask = 200 + 250 / 2 + 150 / 3

    expected = (
        (weighted_bid - weighted_ask)
        / (weighted_bid + weighted_ask)
    )

    assert result.weighted_depth_imbalance == pytest.approx(expected)


def test_bid_liquidity_concentration(order_book):
    result = MicrostructureEngine.calculate(
        order_book,
        concentration_levels=2,
    )

    assert result.bid_liquidity_concentration == pytest.approx(0.8)


def test_ask_liquidity_concentration(order_book):
    result = MicrostructureEngine.calculate(
        order_book,
        concentration_levels=2,
    )

    assert result.ask_liquidity_concentration == pytest.approx(
        450 / 600
    )


def test_invalid_depth_is_rejected(order_book):
    with pytest.raises(ValueError, match="Depth"):
        MicrostructureEngine.calculate(order_book, depth=0)


def test_invalid_concentration_levels_are_rejected(order_book):
    with pytest.raises(ValueError, match="Concentration"):
        MicrostructureEngine.calculate(
            order_book,
            concentration_levels=0,
        )


def test_empty_order_book_side_is_rejected(order_book):
    empty_book = order_book.model_copy(update={"bids": []})

    with pytest.raises(ValueError, match="both bids and asks"):
        MicrostructureEngine.calculate(empty_book)


def test_crossed_order_book_is_rejected(order_book):
    crossed_book = order_book.model_copy(
        update={
            "asks": [
                PriceLevel(price=25999, quantity=200),
                PriceLevel(price=26002, quantity=250),
            ]
        }
    )

    with pytest.raises(ValueError, match="crossed"):
        MicrostructureEngine.calculate(crossed_book)


def test_fewer_levels_than_requested_are_supported(order_book):
    result = MicrostructureEngine.calculate(
        order_book,
        depth=5,
        concentration_levels=5,
    )

    assert result.depth_imbalance == pytest.approx(0.25)
    assert result.bid_liquidity_concentration == pytest.approx(1.0)
    assert result.ask_liquidity_concentration == pytest.approx(1.0)


def test_wrong_instrument_is_preserved_in_result(order_book):
    result = MicrostructureEngine.calculate(order_book)

    assert result.instrument_id == "NIFTY-FUT"
