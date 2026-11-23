
from datetime import UTC, datetime, timedelta

import pytest

from quant_alpha.data.schema import TradeEvent
from quant_alpha.features.tradeflow.engine import TradeFlowEngine


@pytest.fixture
def timestamp():
    return datetime(2026, 11, 23, 9, 15, tzinfo=UTC)


def create_trade(
    timestamp: datetime,
    side: str = "BUY",
    quantity: int = 100,
    instrument_id: str = "NIFTY-FUT",
) -> TradeEvent:
    return TradeEvent(
        instrument_id=instrument_id,
        symbol="NIFTY",
        exchange="NSE",
        provider="test",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        price=26000,
        quantity=quantity,
        aggressor_side=side,
    )


def test_buy_trade_increases_buy_volume(timestamp):
    engine = TradeFlowEngine("NIFTY-FUT")

    result = engine.process_trade(
        create_trade(timestamp, side="BUY", quantity=100)
    )

    assert result.buy_volume == 100
    assert result.sell_volume == 0
    assert result.trade_delta == 100
    assert result.cumulative_volume_delta == 100


def test_sell_trade_decreases_delta(timestamp):
    engine = TradeFlowEngine("NIFTY-FUT")

    result = engine.process_trade(
        create_trade(timestamp, side="SELL", quantity=80)
    )

    assert result.sell_volume == 80
    assert result.trade_delta == -80
    assert result.cumulative_volume_delta == -80


def test_unknown_trade_is_tracked_separately(timestamp):
    engine = TradeFlowEngine("NIFTY-FUT")

    result = engine.process_trade(
        create_trade(timestamp, side="UNKNOWN", quantity=50)
    )

    assert result.unknown_volume == 50
    assert result.buy_volume == 0
    assert result.sell_volume == 0
    assert result.trade_delta == 0
    assert result.cumulative_volume_delta == 0


def test_multiple_trades_calculate_correct_delta(timestamp):
    engine = TradeFlowEngine("NIFTY-FUT")

    engine.process_trade(
        create_trade(timestamp, side="BUY", quantity=100)
    )
    engine.process_trade(
        create_trade(
            timestamp + timedelta(seconds=1),
            side="SELL",
            quantity=40,
        )
    )
    result = engine.process_trade(
        create_trade(
            timestamp + timedelta(seconds=2),
            side="BUY",
            quantity=60,
        )
    )

    assert result.buy_volume == 160
    assert result.sell_volume == 40
    assert result.trade_delta == 120
    assert result.cumulative_volume_delta == 120
    assert result.trade_count == 3


def test_reset_interval_preserves_session_cvd(timestamp):
    engine = TradeFlowEngine("NIFTY-FUT")

    engine.process_trade(
        create_trade(timestamp, side="BUY", quantity=100)
    )
    engine.process_trade(
        create_trade(
            timestamp + timedelta(seconds=1),
            side="SELL",
            quantity=40,
        )
    )

    engine.reset_interval()

    result = engine.process_trade(
        create_trade(
            timestamp + timedelta(seconds=2),
            side="SELL",
            quantity=50,
        )
    )

    assert result.trade_delta == -50
    assert result.cumulative_volume_delta == 10


def test_reset_clears_all_statistics(timestamp):
    engine = TradeFlowEngine("NIFTY-FUT")

    engine.process_trade(
        create_trade(timestamp, side="BUY", quantity=100)
    )
    engine.process_trade(
        create_trade(
            timestamp + timedelta(seconds=1),
            side="UNKNOWN",
            quantity=30,
        )
    )

    engine.reset()
    result = engine.snapshot()

    assert result.buy_volume == 0
    assert result.sell_volume == 0
    assert result.unknown_volume == 0
    assert result.trade_delta == 0
    assert result.cumulative_volume_delta == 0
    assert result.trade_count == 0


def test_wrong_instrument_is_rejected(timestamp):
    engine = TradeFlowEngine("NIFTY-FUT")

    trade = create_trade(
        timestamp,
        instrument_id="BANKNIFTY-FUT",
    )

    with pytest.raises(ValueError, match="Expected NIFTY-FUT"):
        engine.process_trade(trade)


def test_trade_count_includes_unknown_trades(timestamp):
    engine = TradeFlowEngine("NIFTY-FUT")

    engine.process_trade(
        create_trade(timestamp, side="BUY", quantity=100)
    )
    result = engine.process_trade(
        create_trade(
            timestamp + timedelta(seconds=1),
            side="UNKNOWN",
            quantity=50,
        )
    )

    assert result.trade_count == 2

