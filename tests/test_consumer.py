import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from quant_alpha.data.schema import (
    OrderBookSnapshot,
    OrderBookUpdate,
    PriceLevel,
    TradeEvent,
)
from quant_alpha.data.streaming.consumer import MarketDataConsumer
from quant_alpha.data.streaming.event_bus import MarketDataEventBus

BASE_TIME = datetime(2026, 11, 23, 9, 15, tzinfo=UTC)


def create_snapshot(
    instrument_id: str = "NIFTY-FUT",
    sequence_number: int = 100,
    timestamp: datetime = BASE_TIME,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        instrument_id=instrument_id,
        symbol="NIFTY",
        exchange="NSE",
        provider="TEST",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        sequence_number=sequence_number,
        bids=[
            PriceLevel(price=26000.0, quantity=500),
            PriceLevel(price=25999.0, quantity=300),
            PriceLevel(price=25998.0, quantity=200),
        ],
        asks=[
            PriceLevel(price=26001.0, quantity=200),
            PriceLevel(price=26002.0, quantity=250),
            PriceLevel(price=26003.0, quantity=150),
        ],
    )


def create_update(
    instrument_id: str = "NIFTY-FUT",
    sequence_number: int = 101,
    timestamp: datetime = BASE_TIME + timedelta(seconds=1),
) -> OrderBookUpdate:
    return OrderBookUpdate(
        instrument_id=instrument_id,
        symbol="NIFTY",
        exchange="NSE",
        provider="TEST",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        sequence_number=sequence_number,
        side="BID",
        action="UPSERT",
        price=26000.0,
        quantity=550,
    )


def create_trade(
    instrument_id: str = "NIFTY-FUT",
    timestamp: datetime = BASE_TIME,
    quantity: int = 10,
    aggressor_side: str = "BUY",
) -> TradeEvent:
    return TradeEvent(
        instrument_id=instrument_id,
        symbol="NIFTY",
        exchange="NSE",
        provider="TEST",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        trade_id="TRADE-001",
        price=26000.5,
        quantity=quantity,
        aggressor_side=aggressor_side,
    )


def test_register_instrument() -> None:
    consumer = MarketDataConsumer()

    consumer.register_instrument("NIFTY-FUT")

    assert "NIFTY-FUT" in consumer._instruments


def test_register_empty_instrument_id() -> None:
    consumer = MarketDataConsumer()

    with pytest.raises(ValueError):
        consumer.register_instrument("")


def test_register_duplicate_instrument() -> None:
    consumer = MarketDataConsumer()
    consumer.register_instrument("NIFTY-FUT")

    with pytest.raises(ValueError):
        consumer.register_instrument("NIFTY-FUT")


def test_process_event_for_unregistered_instrument() -> None:
    consumer = MarketDataConsumer()

    with pytest.raises(KeyError):
        consumer.process_event(create_trade())



def test_process_order_book_snapshot() -> None:
    consumer = MarketDataConsumer()
    consumer.register_instrument("NIFTY-FUT")

    snapshot = create_snapshot()
    result = consumer.process_event(snapshot)

    assert result.event == snapshot
    assert result.book_snapshot is not None
    assert result.book_snapshot.sequence_number == 100

    assert result.microstructure is not None
    assert result.microstructure.instrument_id == "NIFTY-FUT"
    assert result.microstructure.mid_price == 26000.5
    assert result.microstructure.spread == 1.0


def test_process_order_book_update() -> None:
    consumer = MarketDataConsumer()
    consumer.register_instrument("NIFTY-FUT")

    consumer.process_event(create_snapshot())

    update = create_update()
    result = consumer.process_event(update)

    assert result.book_snapshot is not None
    assert result.book_snapshot.sequence_number == 101

    assert result.ofi is not None
    assert result.ofi.instrument_id == "NIFTY-FUT"
    assert result.ofi.value == 50.0

    assert result.microstructure is not None
    assert result.microstructure.instrument_id == "NIFTY-FUT"


def test_process_trade_event() -> None:
    consumer = MarketDataConsumer()
    consumer.register_instrument("NIFTY-FUT")

    trade = create_trade(quantity=25, aggressor_side="BUY")
    result = consumer.process_event(trade)

    assert result.trade_flow is not None
    assert result.trade_flow.instrument_id == "NIFTY-FUT"
    assert result.trade_flow.buy_volume == 25
    assert result.trade_flow.sell_volume == 0
    assert result.trade_flow.trade_delta == 25
    assert result.trade_flow.cumulative_volume_delta == 25
    assert result.trade_flow.trade_count == 1



def test_order_book_update_before_snapshot_fails() -> None:
    consumer = MarketDataConsumer()
    consumer.register_instrument("NIFTY-FUT")

    with pytest.raises(RuntimeError):
        consumer.process_event(create_update())


def test_instruments_maintain_independent_state() -> None:
    consumer = MarketDataConsumer()

    consumer.register_instrument("NIFTY-FUT")
    consumer.register_instrument("BANKNIFTY-FUT")

    nifty_trade = create_trade(
        instrument_id="NIFTY-FUT",
        quantity=20,
        aggressor_side="BUY",
    )
    banknifty_trade = create_trade(
        instrument_id="BANKNIFTY-FUT",
        quantity=35,
        aggressor_side="SELL",
    )

    nifty_result = consumer.process_event(nifty_trade)
    banknifty_result = consumer.process_event(banknifty_trade)

    assert nifty_result.trade_flow is not None
    assert banknifty_result.trade_flow is not None

    assert nifty_result.trade_flow.buy_volume == 20
    assert nifty_result.trade_flow.sell_volume == 0
    assert nifty_result.trade_flow.cumulative_volume_delta == 20

    assert banknifty_result.trade_flow.buy_volume == 0
    assert banknifty_result.trade_flow.sell_volume == 35
    assert banknifty_result.trade_flow.cumulative_volume_delta == -35

def test_order_book_update_before_snapshot() -> None:
    consumer = MarketDataConsumer()
    consumer.register_instrument("NIFTY-FUT")

    with pytest.raises(RuntimeError):
        consumer.process_event(create_update())


def test_async_consumer_processes_events() -> None:
    async def run_test() -> None:
        bus = MarketDataEventBus(maxsize=10)
        consumer = MarketDataConsumer()
        consumer.register_instrument("NIFTY-FUT")

        results = []

        await bus.publish(create_snapshot())
        await bus.publish(create_trade(quantity=15))
        await bus.close()

        await consumer.run(bus, on_result=results.append)
        await bus.join()

        assert len(results) == 2
        assert results[0].book_snapshot is not None
        assert results[1].trade_flow is not None
        assert results[1].trade_flow.trade_delta == 15

    asyncio.run(run_test())
