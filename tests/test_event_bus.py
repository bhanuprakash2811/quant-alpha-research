
import asyncio
from datetime import UTC, datetime

import pytest

from quant_alpha.data.schema import TradeEvent
from quant_alpha.data.streaming import MarketDataEventBus


def make_trade(
    trade_id: str,
    price: float,
    quantity: int = 10,
) -> TradeEvent:
    timestamp = datetime(2026, 11, 23, 9, 15, tzinfo=UTC)

    return TradeEvent(
        instrument_id="NIFTY-FUT",
        symbol="NIFTY",
        exchange="NSE",
        provider="TEST",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        trade_id=trade_id,
        price=price,
        quantity=quantity,
        aggressor_side="BUY",
    )


def test_event_bus_rejects_invalid_capacity() -> None:
    with pytest.raises(ValueError):
        MarketDataEventBus(maxsize=0)


def test_publish_and_receive_event() -> None:
    async def scenario() -> None:
        bus = MarketDataEventBus()
        event = make_trade("trade-1", 26000.0)

        await bus.publish(event)

        received = await bus.receive()

        assert received == event

        bus.task_done()
        await bus.join()

    asyncio.run(scenario())


def test_events_are_received_in_fifo_order() -> None:
    async def scenario() -> None:
        bus = MarketDataEventBus()

        first = make_trade("trade-1", 26000.0)
        second = make_trade("trade-2", 26001.0)

        await bus.publish(first)
        await bus.publish(second)

        received_first = await bus.receive()
        bus.task_done()

        received_second = await bus.receive()
        bus.task_done()

        assert received_first == first
        assert received_second == second

        await bus.join()

    asyncio.run(scenario())


def test_bounded_queue_applies_backpressure() -> None:
    async def scenario() -> None:
        bus = MarketDataEventBus(maxsize=1)

        first = make_trade("trade-1", 26000.0)
        second = make_trade("trade-2", 26001.0)

        await bus.publish(first)

        blocked_publisher = asyncio.create_task(
            bus.publish(second)
        )

        await asyncio.sleep(0)

        assert not blocked_publisher.done()

        received_first = await bus.receive()
        bus.task_done()

        await blocked_publisher

        received_second = await bus.receive()
        bus.task_done()

        assert received_first == first
        assert received_second == second

        await bus.join()

    asyncio.run(scenario())


def test_close_stops_future_publishing() -> None:
    async def scenario() -> None:
        bus = MarketDataEventBus()
        event = make_trade("trade-1", 26000.0)

        await bus.close()

        assert bus.is_closed

        with pytest.raises(RuntimeError):
            await bus.publish(event)

    asyncio.run(scenario())


def test_close_signal_is_received_after_queued_events() -> None:
    async def scenario() -> None:
        bus = MarketDataEventBus()

        event = make_trade("trade-1", 26000.0)

        await bus.publish(event)
        await bus.close()

        received = await bus.receive()
        bus.task_done()

        shutdown_signal = await bus.receive()

        assert received == event
        assert shutdown_signal is None

        await bus.join()

    asyncio.run(scenario())


def test_close_is_idempotent() -> None:
    async def scenario() -> None:
        bus = MarketDataEventBus()

        await bus.close()
        await bus.close()

        assert bus.is_closed
        assert await bus.receive() is None

    asyncio.run(scenario())
