
from quant_alpha.data.schema import (
    OrderBookSnapshot,
    PriceLevel,
)


class OrderBookEngine:
    """
    Maintains the latest validated order-book snapshot
    for one financial instrument.

    This initial implementation supports complete snapshots.
    Incremental order-book updates will be added separately.
    """

    def __init__(self, instrument_id: str):
        if not instrument_id:
            raise ValueError("Instrument ID cannot be empty.")

        self.instrument_id = instrument_id
        self._snapshot: OrderBookSnapshot | None = None

    def load_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        """
        Replace the current book with a new complete snapshot.
        """

        if snapshot.instrument_id != self.instrument_id:
            raise ValueError(
                f"Expected {self.instrument_id}, "
                f"received {snapshot.instrument_id}."
            )

        self._snapshot = snapshot

    @property
    def is_initialized(self) -> bool:
        return self._snapshot is not None

    def _require_snapshot(self) -> OrderBookSnapshot:
        if self._snapshot is None:
            raise RuntimeError(
                "Order book is not initialized. "
                "Load a snapshot first."
            )

        return self._snapshot

    @property
    def best_bid(self) -> PriceLevel | None:
        snapshot = self._require_snapshot()

        return snapshot.bids[0] if snapshot.bids else None

    @property
    def best_ask(self) -> PriceLevel | None:
        snapshot = self._require_snapshot()

        return snapshot.asks[0] if snapshot.asks else None

    @property
    def spread(self) -> float | None:
        bid = self.best_bid
        ask = self.best_ask

        if bid is None or ask is None:
            return None

        return ask.price - bid.price

    @property
    def mid_price(self) -> float | None:
        bid = self.best_bid
        ask = self.best_ask

        if bid is None or ask is None:
            return None

        return (bid.price + ask.price) / 2

    def depth_imbalance(self, depth: int = 5) -> float | None:
        """
        Calculate bid/ask quantity imbalance.

        Formula:

        (Bid quantity - Ask quantity)
        --------------------------------
        (Bid quantity + Ask quantity)

        Result ranges from -1 to +1.
        """

        if depth <= 0:
            raise ValueError("Depth must be greater than zero.")

        snapshot = self._require_snapshot()

        bid_quantity = sum(
            level.quantity for level in snapshot.bids[:depth]
        )

        ask_quantity = sum(
            level.quantity for level in snapshot.asks[:depth]
        )

        total_quantity = bid_quantity + ask_quantity

        if total_quantity == 0:
            return None

        return (
            (bid_quantity - ask_quantity)
            / total_quantity
        )
