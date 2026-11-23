
import asyncio
from enum import Enum
from typing import TypeAlias

from quant_alpha.data.schema import (
    OrderBookSnapshot,
    OrderBookUpdate,
    TradeEvent,
)

MarketDataEvent: TypeAlias = (
    TradeEvent | OrderBookSnapshot | OrderBookUpdate
)


class _StopSignal(Enum):
    STOP = "stop"


class MarketDataEventBus:
    """
    Bounded asynchronous FIFO bus for normalized market-data events.

    This initial implementation is designed for one consumer.
    """

    def __init__(self, maxsize: int = 10_000) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be greater than zero.")

        self._queue: asyncio.Queue[
            MarketDataEvent | _StopSignal
        ] = asyncio.Queue(maxsize=maxsize)

        self._publish_lock = asyncio.Lock()
        self._closed = False

    async def publish(self, event: MarketDataEvent) -> None:
        """Publish an event, waiting if the queue is full."""
        async with self._publish_lock:
            if self._closed:
                raise RuntimeError("Cannot publish to a closed event bus.")

            await self._queue.put(event)

    async def receive(self) -> MarketDataEvent | None:
        """
        Receive the next event.

        Returns None after the shutdown signal is received.
        """
        item = await self._queue.get()

        if item is _StopSignal.STOP:
            self._queue.task_done()
            return None

        return item

    def task_done(self) -> None:
        """Acknowledge successful processing of one received event."""
        self._queue.task_done()

    async def join(self) -> None:
        """Wait until all queued events have been acknowledged."""
        await self._queue.join()

    async def close(self) -> None:
        """Stop accepting new events and enqueue a shutdown signal."""
        async with self._publish_lock:
            if self._closed:
                return

            self._closed = True
            await self._queue.put(_StopSignal.STOP)

    def qsize(self) -> int:
        """Return the current number of queued items."""
        return self._queue.qsize()

    @property
    def is_closed(self) -> bool:
        return self._closed
