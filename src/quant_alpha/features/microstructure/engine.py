
from dataclasses import dataclass

from quant_alpha.data.schema import OrderBookSnapshot


@dataclass(frozen=True)
class MicrostructureFeatures:
    instrument_id: str
    mid_price: float
    microprice: float
    spread: float
    spread_bps: float
    depth_imbalance: float
    weighted_depth_imbalance: float
    bid_liquidity_concentration: float
    ask_liquidity_concentration: float


class MicrostructureEngine:
    """
    Calculates quantitative microstructure features
    from an order-book snapshot.
    """

    @staticmethod
    def calculate(
        snapshot: OrderBookSnapshot,
        depth: int = 5,
        concentration_levels: int = 3,
    ) -> MicrostructureFeatures:

        if depth <= 0:
            raise ValueError("Depth must be greater than zero.")

        if concentration_levels <= 0:
            raise ValueError(
                "Concentration levels must be greater than zero."
            )

        if not snapshot.bids or not snapshot.asks:
            raise ValueError(
                "Order book must contain both bids and asks."
            )

        best_bid = snapshot.bids[0]
        best_ask = snapshot.asks[0]

        if best_bid.price > best_ask.price:
            raise ValueError("Order book is crossed.")

        mid_price = (best_bid.price + best_ask.price) / 2
        spread = best_ask.price - best_bid.price

        if mid_price <= 0:
            raise ValueError("Mid-price must be positive.")

        spread_bps = (spread / mid_price) * 10000

        # Multi-level depth imbalance
        bid_levels = snapshot.bids[:depth]
        ask_levels = snapshot.asks[:depth]

        bid_quantity = sum(level.quantity for level in bid_levels)
        ask_quantity = sum(level.quantity for level in ask_levels)

        total_depth = bid_quantity + ask_quantity

        if total_depth == 0:
            raise ValueError("Total market depth cannot be zero.")

        depth_imbalance = (
            bid_quantity - ask_quantity
        ) / total_depth

        # Weighted depth imbalance
        weighted_bid = sum(
            level.quantity / (index + 1)
            for index, level in enumerate(bid_levels)
        )

        weighted_ask = sum(
            level.quantity / (index + 1)
            for index, level in enumerate(ask_levels)
        )

        weighted_total = weighted_bid + weighted_ask

        weighted_depth_imbalance = (
            weighted_bid - weighted_ask
        ) / weighted_total

        # Microprice
        top_quantity = best_bid.quantity + best_ask.quantity

        microprice = (
            best_ask.price * best_bid.quantity
            + best_bid.price * best_ask.quantity
        ) / top_quantity

        # Liquidity concentration
        total_bid_liquidity = sum(
            level.quantity for level in snapshot.bids
        )

        total_ask_liquidity = sum(
            level.quantity for level in snapshot.asks
        )

        top_bid_liquidity = sum(
            level.quantity
            for level in snapshot.bids[:concentration_levels]
        )

        top_ask_liquidity = sum(
            level.quantity
            for level in snapshot.asks[:concentration_levels]
        )

        bid_concentration = (
            top_bid_liquidity / total_bid_liquidity
        )

        ask_concentration = (
            top_ask_liquidity / total_ask_liquidity
        )

        return MicrostructureFeatures(
            instrument_id=snapshot.instrument_id,
            mid_price=mid_price,
            microprice=microprice,
            spread=spread,
            spread_bps=spread_bps,
            depth_imbalance=depth_imbalance,
            weighted_depth_imbalance=weighted_depth_imbalance,
            bid_liquidity_concentration=bid_concentration,
            ask_liquidity_concentration=ask_concentration,
        )
