
from dataclasses import dataclass

from quant_alpha.data.schema import OrderBookSnapshot


@dataclass(frozen=True)
class OFIResult:
    instrument_id: str
    bid_component: float
    ask_component: float
    value: float


class OrderFlowImbalanceCalculator:
    """
    Calculates best-level Order Flow Imbalance (OFI)
    between two consecutive order-book snapshots.

    Positive OFI indicates net buying-side pressure.
    Negative OFI indicates net selling-side pressure.
    """

    @staticmethod
    def calculate(
        previous: OrderBookSnapshot,
        current: OrderBookSnapshot,
    ) -> OFIResult:

        if previous.instrument_id != current.instrument_id:
            raise ValueError("Snapshots must belong to the same instrument.")

        if current.exchange_timestamp <= previous.exchange_timestamp:
            raise ValueError("Current snapshot must have a later timestamp.")

        if not previous.bids or not previous.asks:
            raise ValueError("Previous snapshot must contain bids and asks.")

        if not current.bids or not current.asks:
            raise ValueError("Current snapshot must contain bids and asks.")

        previous_bid = previous.bids[0]
        current_bid = current.bids[0]

        previous_ask = previous.asks[0]
        current_ask = current.asks[0]

        # Bid-side contribution
        if current_bid.price > previous_bid.price:
            bid_component = current_bid.quantity
        elif current_bid.price < previous_bid.price:
            bid_component = -previous_bid.quantity
        else:
            bid_component = (
                current_bid.quantity - previous_bid.quantity
            )

        # Ask-side contribution
        if current_ask.price < previous_ask.price:
            ask_component = -current_ask.quantity
        elif current_ask.price > previous_ask.price:
            ask_component = previous_ask.quantity
        else:
            ask_component = (
                previous_ask.quantity - current_ask.quantity
            )

        return OFIResult(
            instrument_id=current.instrument_id,
            bid_component=bid_component,
            ask_component=ask_component,
            value=bid_component + ask_component,
        )
