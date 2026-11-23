
from collections.abc import Callable
from dataclasses import dataclass

from quant_alpha.data.schema import (
    OrderBookSnapshot,
    OrderBookUpdate,
    TradeEvent,
)
from quant_alpha.data.streaming.event_bus import (
    MarketDataEvent,
    MarketDataEventBus,
)
from quant_alpha.features.market_depth.incremental import (
    IncrementalOrderBook,
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

            return MarketDataProcessingResult(
                event=event,
                trade_flow=trade_flow,
            )

        if isinstance(event, OrderBookSnapshot):
            # Validate analytics before replacing the current book.
            microstructure = MicrostructureEngine.calculate(event)

            state.order_book.load_snapshot(event)
            snapshot = state.order_book.get_snapshot()
            state.previous_snapshot = snapshot

            return MarketDataProcessingResult(
                event=event,
                book_snapshot=snapshot,
                microstructure=microstructure,
            )

        if isinstance(event, OrderBookUpdate):
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

            return MarketDataProcessingResult(
                event=event,
                book_snapshot=current,
                ofi=ofi,
                microstructure=microstructure,
            )

        # Defensive guard in case the event union is extended.
        raise TypeError(
            f"Unsupported market event type: {type(event).__name__}."
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

