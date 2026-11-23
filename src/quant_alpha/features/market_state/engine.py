
from dataclasses import dataclass
from datetime import datetime

from quant_alpha.data.schema import (
    MarketEvent,
    OrderBookSnapshot,
    OrderBookUpdate,
    TradeEvent,
)
from quant_alpha.features.microstructure.engine import (
    MicrostructureFeatures,
)
from quant_alpha.features.orderflow.ofi import OFIResult
from quant_alpha.features.tradeflow.engine import TradeFlowSnapshot


@dataclass(frozen=True)
class MarketState:
    """Unified latest market state for one instrument."""

    instrument_id: str

    book_snapshot: OrderBookSnapshot | None = None
    trade_flow: TradeFlowSnapshot | None = None
    ofi: OFIResult | None = None
    microstructure: MicrostructureFeatures | None = None

    last_trade_exchange_timestamp: datetime | None = None
    last_trade_received_timestamp: datetime | None = None

    last_book_exchange_timestamp: datetime | None = None
    last_book_received_timestamp: datetime | None = None

    last_event_exchange_timestamp: datetime | None = None
    last_event_received_timestamp: datetime | None = None

    book_valid: bool | None = None


class MarketStateEngine:
    """
    Maintains a unified market state independently for each instrument.

    Only successfully processed events should be passed to update().
    """

    def __init__(self) -> None:
        self._states: dict[str, MarketState] = {}

    def register_instrument(self, instrument_id: str) -> None:
        """Register an instrument with an initially empty state."""

        if not instrument_id:
            raise ValueError("Instrument ID cannot be empty.")

        if instrument_id in self._states:
            raise ValueError(
                f"Instrument already registered: {instrument_id}."
            )

        self._states[instrument_id] = MarketState(
            instrument_id=instrument_id,
        )

    def update(
        self,
        event: MarketEvent,
        *,
        book_snapshot: OrderBookSnapshot | None = None,
        trade_flow: TradeFlowSnapshot | None = None,
        ofi: OFIResult | None = None,
        microstructure: MicrostructureFeatures | None = None,
    ) -> MarketState:
        """Merge the outputs of a processed event into its instrument state."""

        instrument_id = event.instrument_id
        current = self._states.get(instrument_id)

        if current is None:
            raise KeyError(
                f"Instrument is not registered: {instrument_id}."
            )

        if isinstance(event, TradeEvent):
            if trade_flow is None:
                raise ValueError(
                    "Trade events require a trade-flow snapshot."
                )

            if trade_flow.instrument_id != instrument_id:
                raise ValueError("Trade-flow instrument mismatch.")

            updated = MarketState(
                **{
                    **current.__dict__,
                    "trade_flow": trade_flow,
                    "last_trade_exchange_timestamp": (
                        event.exchange_timestamp
                    ),
                    "last_trade_received_timestamp": (
                        event.received_timestamp
                    ),
                    "last_event_exchange_timestamp": (
                        event.exchange_timestamp
                    ),
                    "last_event_received_timestamp": (
                        event.received_timestamp
                    ),
                }
            )

        elif isinstance(event, (OrderBookSnapshot, OrderBookUpdate)):
            if book_snapshot is None or microstructure is None:
                raise ValueError(
                    "Order-book events require a book snapshot "
                    "and microstructure features."
                )

            if book_snapshot.instrument_id != instrument_id:
                raise ValueError("Order-book instrument mismatch.")

            if microstructure.instrument_id != instrument_id:
                raise ValueError("Microstructure instrument mismatch.")

            if ofi is not None and ofi.instrument_id != instrument_id:
                raise ValueError("OFI instrument mismatch.")

            updated = MarketState(
                **{
                    **current.__dict__,
                    "book_snapshot": book_snapshot,
                    "microstructure": microstructure,
                    "ofi": ofi if ofi is not None else current.ofi,
                    "last_book_exchange_timestamp": (
                        event.exchange_timestamp
                    ),
                    "last_book_received_timestamp": (
                        event.received_timestamp
                    ),
                    "last_event_exchange_timestamp": (
                        event.exchange_timestamp
                    ),
                    "last_event_received_timestamp": (
                        event.received_timestamp
                    ),
                    "book_valid": True,
                }
            )

        else:
            raise TypeError(
                f"Unsupported event type: {type(event).__name__}."
            )

        self._states[instrument_id] = updated
        return updated

    def get_state(self, instrument_id: str) -> MarketState:
        """Return the latest state for an instrument."""

        state = self._states.get(instrument_id)

        if state is None:
            raise KeyError(
                f"Instrument is not registered: {instrument_id}."
            )

        return state

    def registered_instruments(self) -> tuple[str, ...]:
        """Return registered instrument IDs."""

        return tuple(self._states)
