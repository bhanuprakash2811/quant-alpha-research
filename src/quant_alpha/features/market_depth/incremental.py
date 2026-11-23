
from quant_alpha.data.schema import (
    OrderBookSnapshot,
    OrderBookUpdate,
)


class IncrementalOrderBook:
    """
    Maintains an order book using an initial snapshot
    followed by incremental Level 2 updates.

    Sequence numbers are assumed to be consecutive
    in this initial normalized feed implementation.
    """

    def __init__(self, instrument_id: str) -> None:
        if not instrument_id:
            raise ValueError("Instrument ID cannot be empty.")

        self.instrument_id = instrument_id

        self._bids: dict[float, int] = {}
        self._asks: dict[float, int] = {}

        self._snapshot_template: OrderBookSnapshot | None = None
        self._last_sequence_number: int | None = None

        self._is_valid = False
        self._invalid_reason: str | None = "Initial snapshot not loaded."

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    @property
    def last_sequence_number(self) -> int | None:
        return self._last_sequence_number

    @property
    def invalid_reason(self) -> str | None:
        return self._invalid_reason

    def _invalidate(self, reason: str) -> None:
        self._is_valid = False
        self._invalid_reason = reason

    def load_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        """
        Load a complete snapshot and synchronize sequence state.
        A fresh snapshot restores a previously invalid book.
        """

        if snapshot.instrument_id != self.instrument_id:
            raise ValueError(
                f"Expected {self.instrument_id}, "
                f"received {snapshot.instrument_id}."
            )

        if snapshot.sequence_number is None:
            raise ValueError(
                "Snapshot must contain a sequence number."
            )

        self._bids = {
            level.price: level.quantity
            for level in snapshot.bids
        }

        self._asks = {
            level.price: level.quantity
            for level in snapshot.asks
        }

        self._snapshot_template = snapshot
        self._last_sequence_number = snapshot.sequence_number

        self._is_valid = True
        self._invalid_reason = None

    def apply_update(
        self,
        update: OrderBookUpdate,
    ) -> OrderBookSnapshot:
        """Apply an update atomically and return the updated book."""

        if not self._is_valid:
            raise RuntimeError(
                "Order book is invalid. Load a fresh snapshot first. "
                f"Reason: {self._invalid_reason}"
            )

        if update.instrument_id != self.instrument_id:
            raise ValueError(
                f"Expected {self.instrument_id}, "
                f"received {update.instrument_id}."
            )

        if self._last_sequence_number is None:
            raise RuntimeError("Order book sequence is not initialized.")
        sequence_number = update.sequence_number

        if sequence_number is None:
            raise ValueError("Update must contain a sequence number.")

        expected_sequence = self._last_sequence_number + 1

        sequence_number = update.sequence_number
        if sequence_number is None:
            raise ValueError("Update must contain a sequence number.")

        if sequence_number != expected_sequence:
            if sequence_number > expected_sequence:
                reason = (
                    f"Sequence gap detected. Expected "
                    f"{expected_sequence}, received "
                    f"{sequence_number}."
                )
                self._invalidate(reason)
                raise RuntimeError(reason)

            raise ValueError(
                f"Stale or duplicate update. Expected "
                f"{expected_sequence}, received "
                f"{sequence_number}."
            )

        # Work on temporary copies.
        new_bids = self._bids.copy()
        new_asks = self._asks.copy()

        book_side = new_bids if update.side == "BID" else new_asks

        if update.action == "UPSERT":
            if update.quantity is None:
                raise ValueError("UPSERT requires a quantity.")

            book_side[update.price] = update.quantity

        elif update.action == "DELETE":
            if update.price not in book_side:
                reason = (
                    f"Cannot delete missing {update.side} "
                    f"price level: {update.price}."
                )
                self._invalidate(reason)
                raise RuntimeError(reason)

            del book_side[update.price]

        # Validate the temporary book before committing.
        try:
            candidate_snapshot = self._build_snapshot(
                bids=new_bids,
                asks=new_asks,
                sequence_number=sequence_number,
                latest_update=update,
            )
        except ValueError as exc:
            reason = f"Invalid order book after update: {exc}"
            self._invalidate(reason)
            raise RuntimeError(reason) from exc

        # Commit only after successful validation.
        self._bids = new_bids
        self._asks = new_asks
        self._last_sequence_number = sequence_number
        self._snapshot_template = candidate_snapshot

        return candidate_snapshot
    
    def get_snapshot(
        self,
        latest_update: OrderBookUpdate | None = None,
    ) -> OrderBookSnapshot:
        """Build a validated snapshot from the current in-memory book."""

        if not self._is_valid or self._snapshot_template is None:
            raise RuntimeError(
                "Cannot read an invalid or uninitialized order book."
            )

        if self._last_sequence_number is None:
            raise RuntimeError("Order book sequence is not initialized.")

        return self._build_snapshot(
            bids=self._bids,
            asks=self._asks,
            sequence_number=self._last_sequence_number,
            latest_update=latest_update,
        )


    def _build_snapshot(
        self,
        bids: dict[float, int],
        asks: dict[float, int],
        sequence_number: int,
        latest_update: OrderBookUpdate | None = None,
    ) -> OrderBookSnapshot:
        """Build and validate an order-book snapshot."""
        if self._snapshot_template is None:
            raise RuntimeError("Snapshot template is not initialized.")
        
        if not bids or not asks:
            raise ValueError("Both bid and ask sides must be non-empty.")

        sorted_bids = sorted(bids.items(), reverse=True)
        sorted_asks = sorted(asks.items())

        best_bid = sorted_bids[0][0]
        best_ask = sorted_asks[0][0]

        if best_bid > best_ask:
            raise ValueError(
                f"Crossed order book detected: "
                f"best bid {best_bid}, best ask {best_ask}."
            )

        payload: dict[str, object] = self._snapshot_template.model_dump()

        payload.update(
            {
                "bids": [
                    {"price": price, "quantity": quantity}
                    for price, quantity in sorted_bids
                ],
                "asks": [
                    {"price": price, "quantity": quantity}
                    for price, quantity in sorted_asks
                ],
                "sequence_number": sequence_number,
            }
        )

        if latest_update is not None:
            payload.update(
                {
                    "exchange_timestamp": latest_update.exchange_timestamp,
                    "received_timestamp": latest_update.received_timestamp,
                }
            )

        return OrderBookSnapshot.model_validate(payload)
