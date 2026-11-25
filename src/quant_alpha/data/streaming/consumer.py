
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from quant_alpha.data.schema import (
    OrderBookSnapshot,
    OrderBookUpdate,
    TradeEvent,
)
from quant_alpha.data.streaming.event_bus import (
    MarketDataEvent,
    MarketDataEventBus,
)
from quant_alpha.data.streaming.health import (
    FeedHealthSnapshot,
    MarketDataFeedMonitor,
)
from quant_alpha.features.market_depth.incremental import (
    IncrementalOrderBook,
)
from quant_alpha.features.market_state import (
    MarketState,
    MarketStateEngine,
)
from quant_alpha.features.microstructure.engine import (
    MicrostructureEngine,
    MicrostructureFeatures,
)
from quant_alpha.features.orderflow.ofi import (
    OFIResult,
    OrderFlowImbalanceCalculator,
)
from quant_alpha.features.tradeflow.engine import (
    TradeFlowEngine,
    TradeFlowSnapshot,
)


@dataclass(frozen=True)
class MarketDataProcessingResult:
    """Analytics produced while processing one market event."""

    event: MarketDataEvent
    book_snapshot: OrderBookSnapshot | None = None
    trade_flow: TradeFlowSnapshot | None = None
    ofi: OFIResult | None = None
    microstructure: MicrostructureFeatures | None = None
    market_state: MarketState | None = None
    feed_health: FeedHealthSnapshot | None = None


@dataclass
class _InstrumentState:
    """Independent processing state for one instrument."""

    order_book: IncrementalOrderBook
    trade_flow: TradeFlowEngine
    previous_snapshot: OrderBookSnapshot | None = None


class MarketDataConsumer:
    """
    Dispatch normalized events to the appropriate instrument engines.

    Each instrument has an independent order book and trade-flow engine.
    """

    def __init__(self) -> None:
        self._instruments: dict[str, _InstrumentState] = {}
        self._market_state = MarketStateEngine()
        self._feed_monitor = MarketDataFeedMonitor()

    def register_instrument(self, instrument_id: str) -> None:
        """Create analytics engines for an instrument."""
        if not instrument_id:
            raise ValueError("Instrument ID cannot be empty.")

        if instrument_id in self._instruments:
            raise ValueError(
                f"Instrument already registered: {instrument_id}."
            )

        self._instruments[instrument_id] = _InstrumentState(
            order_book=IncrementalOrderBook(instrument_id),
            trade_flow=TradeFlowEngine(instrument_id),
        )
        self._market_state.register_instrument(instrument_id)

    def process_event(
        self,
        event: MarketDataEvent,
    ) -> MarketDataProcessingResult:
        """Process one normalized event and return its analytics."""

        state = self._instruments.get(event.instrument_id)

        if state is None:
            raise KeyError(
                f"Instrument is not registered: {event.instrument_id}."
            )

        if isinstance(event, TradeEvent):
            trade_flow = state.trade_flow.process_trade(event)

            result = MarketDataProcessingResult(
                event=event,
                trade_flow=trade_flow,
            )
        elif isinstance(event, OrderBookSnapshot):
            # Validate analytics before replacing the current book.
            microstructure = MicrostructureEngine.calculate(event)

            state.order_book.load_snapshot(event)
            snapshot = state.order_book.get_snapshot()
            state.previous_snapshot = snapshot

            result = MarketDataProcessingResult(
                event=event,
                book_snapshot=snapshot,
                microstructure=microstructure,
            )
        elif isinstance(event, OrderBookUpdate):
            previous = state.order_book.get_snapshot()
            current = state.order_book.apply_update(event)

            ofi = None

            if current.exchange_timestamp > previous.exchange_timestamp:
                ofi = OrderFlowImbalanceCalculator.calculate(
                    previous,
                    current,
                )

            microstructure = MicrostructureEngine.calculate(current)
            state.previous_snapshot = current

            result = MarketDataProcessingResult(
                event=event,
                book_snapshot=current,
                ofi=ofi,
                microstructure=microstructure,
            )
        else:
            # Defensive guard in case the event union is extended.
            raise TypeError(
                f"Unsupported market event type: {type(event).__name__}."
            )

        market_state = self._market_state.update(
            event,
            book_snapshot=result.book_snapshot,
            trade_flow=result.trade_flow,
            ofi=result.ofi,
            microstructure=result.microstructure,
        )
        self._feed_monitor.record_event(event)
        feed_health = self._feed_monitor.get_health(
            provider=event.provider,
            instrument_id=event.instrument_id,
            now=event.received_timestamp,
        )

        return MarketDataProcessingResult(
            event=result.event,
            book_snapshot=result.book_snapshot,
            trade_flow=result.trade_flow,
            ofi=result.ofi,
            microstructure=result.microstructure,
            market_state=market_state,
            feed_health=feed_health,
        )

    def get_market_state(self, instrument_id: str) -> MarketState:
        """Return the latest unified state for a registered instrument."""

        return self._market_state.get_state(instrument_id)

    def get_feed_health(
        self,
        provider: str,
        instrument_id: str,
        *,
        now: datetime | None = None,
    ) -> FeedHealthSnapshot:
        """Return current freshness and delivery latency for a feed."""

        return self._feed_monitor.get_health(
            provider,
            instrument_id,
            now=now,
        )

    async def run(
        self,
        bus: MarketDataEventBus,
        on_result: Callable[
            [MarketDataProcessingResult], None
        ] | None = None,
    ) -> None:
        """
        Consume events until the bus sends its shutdown signal.

        Processing is fail-fast: an event-processing or callback error
        stops this consumer and propagates to its caller.
        """
        while True:
            event = await bus.receive()

            if event is None:
                return

            try:
                result = self.process_event(event)

                if on_result is not None:
                    on_result(result)

            finally:
                # Always acknowledge the dequeued event, even on failure.
                bus.task_done()

