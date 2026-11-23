
from dataclasses import dataclass

from quant_alpha.data.schema import TradeEvent


@dataclass(frozen=True)
class TradeFlowSnapshot:
    instrument_id: str
    buy_volume: int
    sell_volume: int
    unknown_volume: int
    trade_delta: int
    cumulative_volume_delta: int
    trade_count: int


class TradeFlowEngine:
    """
    Tracks executed trade volume by aggressor side.

    BUY: buyer-initiated executed volume.
    SELL: seller-initiated executed volume.
    UNKNOWN: volume whose aggressor side is unavailable.

    CVD is the running sum of trade delta.
    """

    def __init__(self, instrument_id: str) -> None:
        if not instrument_id:
            raise ValueError("Instrument ID cannot be empty.")

        self.instrument_id = instrument_id
        self.reset()

    def reset(self) -> None:
        """Reset all statistics for a new trading session."""
        self._buy_volume = 0
        self._sell_volume = 0
        self._unknown_volume = 0
        self._trade_delta = 0
        self._cumulative_volume_delta = 0
        self._trade_count = 0

    def process_trade(self, trade: TradeEvent) -> TradeFlowSnapshot:
        """Process one trade and return the updated statistics."""

        if trade.instrument_id != self.instrument_id:
            raise ValueError(
                f"Expected {self.instrument_id}, "
                f"received {trade.instrument_id}."
            )

        if trade.aggressor_side == "BUY":
            self._buy_volume += trade.quantity
            self._trade_delta += trade.quantity

        elif trade.aggressor_side == "SELL":
            self._sell_volume += trade.quantity
            self._trade_delta -= trade.quantity

        else:
            self._unknown_volume += trade.quantity

        self._cumulative_volume_delta += (
            trade.quantity
            if trade.aggressor_side == "BUY"
            else -trade.quantity
            if trade.aggressor_side == "SELL"
            else 0
        )

        self._trade_count += 1

        return self.snapshot()

    def snapshot(self) -> TradeFlowSnapshot:
        """Return the current trade-flow statistics."""

        return TradeFlowSnapshot(
            instrument_id=self.instrument_id,
            buy_volume=self._buy_volume,
            sell_volume=self._sell_volume,
            unknown_volume=self._unknown_volume,
            trade_delta=self._trade_delta,
            cumulative_volume_delta=self._cumulative_volume_delta,
            trade_count=self._trade_count,
        )
    def reset_interval(self) -> None:
        """Reset interval delta without resetting session CVD."""
        self._trade_delta = 0
