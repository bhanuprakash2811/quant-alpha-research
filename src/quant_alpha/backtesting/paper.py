"""Simple order-book-driven paper execution for research workflows.

This simulator assumes displayed depth is executable and does not model queue
position, hidden liquidity, venue priority, latency, or exchange fees beyond an
optional proportional commission. Results are for simulation only.
"""

from dataclasses import dataclass, replace
from enum import Enum
from math import isfinite

from quant_alpha.data.schema import OrderBookSnapshot


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class PaperOrder:
    order_id: str
    instrument_id: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: float | None
    filled_quantity: int = 0
    status: OrderStatus = OrderStatus.OPEN

    @property
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    order_id: str
    instrument_id: str
    side: OrderSide
    quantity: int
    price: float
    fee: float
    sequence_number: int | None


@dataclass
class PaperPosition:
    instrument_id: str
    quantity: int = 0
    average_price: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class PaperAccountSnapshot:
    cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    fees_paid: float


class PaperBroker:
    """Simulate market and limit orders against recent displayed depth.

    Market orders use the currently visible opposing depth and expire any
    remainder (IOC behavior). Limit orders remain open and are rechecked when
    a new snapshot is supplied with :meth:`on_book_snapshot`.
    """

    def __init__(
        self,
        *,
        initial_cash: float = 1_000_000.0,
        commission_bps: float = 0.0,
    ) -> None:
        if not isfinite(initial_cash) or initial_cash < 0:
            raise ValueError("initial_cash must be a finite non-negative value.")
        if not isfinite(commission_bps) or commission_bps < 0:
            raise ValueError("commission_bps must be finite and non-negative.")

        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._commission_rate = commission_bps / 10_000
        self._fees_paid = 0.0
        self._orders: dict[str, PaperOrder] = {}
        self._fills: list[PaperFill] = []
        self._positions: dict[str, PaperPosition] = {}
        self._books: dict[str, OrderBookSnapshot] = {}
        self._liquidity: dict[str, dict[str, list[list[float]]]] = {}
        self._order_counter = 0
        self._fill_counter = 0

    def submit_order(
        self,
        instrument_id: str,
        side: OrderSide | str,
        quantity: int,
        order_type: OrderType | str = OrderType.MARKET,
        *,
        limit_price: float | None = None,
    ) -> PaperOrder:
        """Submit an order and return a copy of its current state."""

        if not instrument_id:
            raise ValueError("Instrument ID cannot be empty.")
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            raise ValueError("quantity must be a positive integer.")

        order_side = OrderSide(side)
        kind = OrderType(order_type)
        if kind is OrderType.LIMIT:
            if limit_price is None or not isfinite(limit_price) or limit_price <= 0:
                raise ValueError("Limit orders require a finite positive price.")
        elif limit_price is not None:
            raise ValueError("Market orders cannot specify a limit price.")

        self._order_counter += 1
        order_id = f"PAPER-{self._order_counter:08d}"
        order = PaperOrder(
            order_id=order_id,
            instrument_id=instrument_id,
            side=order_side,
            order_type=kind,
            quantity=quantity,
            limit_price=limit_price,
        )
        self._orders[order_id] = order

        self._try_fill(order)
        if kind is OrderType.MARKET and order.remaining_quantity:
            order.status = OrderStatus.EXPIRED

        return replace(order)

    def cancel_order(self, order_id: str) -> PaperOrder:
        """Cancel an open limit order."""

        order = self._require_order(order_id)
        if order.status not in {
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        }:
            raise ValueError(f"Order is not open: {order_id}.")
        order.status = OrderStatus.CANCELLED
        return replace(order)

    def on_book_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        """Refresh visible liquidity and try to execute resting limit orders."""

        self._books[snapshot.instrument_id] = snapshot
        self._liquidity[snapshot.instrument_id] = {
            "asks": [[level.price, float(level.quantity)] for level in snapshot.asks],
            "bids": [[level.price, float(level.quantity)] for level in snapshot.bids],
        }

        resting = [
            order
            for order in self._orders.values()
            if (
                order.instrument_id == snapshot.instrument_id
                and order.order_type is OrderType.LIMIT
                and order.status in {
                    OrderStatus.OPEN,
                    OrderStatus.PARTIALLY_FILLED,
                }
            )
        ]
        for side in (OrderSide.BUY, OrderSide.SELL):
            side_orders = [order for order in resting if order.side is side]
            side_orders.sort(
                key=lambda order: (
                    (-1 if side is OrderSide.BUY else 1)
                    * (order.limit_price or 0.0),
                    order.order_id,
                )
            )
            for order in side_orders:
                self._try_fill(order)

    def get_order(self, order_id: str) -> PaperOrder:
        """Return a copy of an order by ID."""

        return replace(self._require_order(order_id))

    def orders(self) -> tuple[PaperOrder, ...]:
        """Return copies of all orders in submission order."""

        return tuple(replace(order) for order in self._orders.values())

    def fills(self) -> tuple[PaperFill, ...]:
        """Return the immutable execution history."""

        return tuple(self._fills)

    def positions(self) -> tuple[PaperPosition, ...]:
        """Return copies of non-flat instrument positions."""

        return tuple(
            replace(position)
            for position in self._positions.values()
            if position.quantity != 0
        )

    def account(self) -> PaperAccountSnapshot:
        """Return cash, marked equity, and realized/unrealized P&L."""

        unrealized = 0.0
        for instrument_id, position in self._positions.items():
            if position.quantity == 0:
                continue
            book = self._books.get(instrument_id)
            if book is not None and book.bids and book.asks:
                mark = (book.bids[0].price + book.asks[0].price) / 2
                unrealized += (mark - position.average_price) * position.quantity

        realized = sum(p.realized_pnl for p in self._positions.values())
        return PaperAccountSnapshot(
            cash=self._cash,
            equity=self._cash + sum(
                position.quantity * self._mark_price(position.instrument_id)
                for position in self._positions.values()
            ),
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            fees_paid=self._fees_paid,
        )

    def reset(self) -> None:
        """Clear simulated activity and restore the configured starting cash."""

        self._cash = self._initial_cash
        self._fees_paid = 0.0
        self._orders.clear()
        self._fills.clear()
        self._positions.clear()
        self._books.clear()
        self._liquidity.clear()
        self._order_counter = 0
        self._fill_counter = 0

    def _try_fill(self, order: PaperOrder) -> None:
        liquidity = self._liquidity.get(order.instrument_id)
        if liquidity is None or order.remaining_quantity == 0:
            return

        levels = liquidity["asks" if order.side is OrderSide.BUY else "bids"]
        for level in levels:
            if order.remaining_quantity == 0:
                break
            price, available = level
            if order.limit_price is not None:
                if order.side is OrderSide.BUY and price > order.limit_price:
                    break
                if order.side is OrderSide.SELL and price < order.limit_price:
                    break

            quantity = min(order.remaining_quantity, int(available))
            if quantity <= 0:
                continue
            level[1] -= quantity
            self._apply_fill(order, quantity, price)

        if order.remaining_quantity == 0:
            order.status = OrderStatus.FILLED
        elif order.filled_quantity:
            order.status = OrderStatus.PARTIALLY_FILLED

    def _apply_fill(self, order: PaperOrder, quantity: int, price: float) -> None:
        notional = quantity * price
        fee = notional * self._commission_rate
        signed_quantity = quantity if order.side is OrderSide.BUY else -quantity
        self._cash -= signed_quantity * price
        self._cash -= fee
        self._fees_paid += fee
        order.filled_quantity += quantity

        position = self._positions.setdefault(
            order.instrument_id,
            PaperPosition(instrument_id=order.instrument_id),
        )
        old_quantity = position.quantity
        new_quantity = old_quantity + signed_quantity
        if old_quantity == 0 or old_quantity * signed_quantity > 0:
            total = abs(old_quantity) + quantity
            position.average_price = (
                abs(old_quantity) * position.average_price + quantity * price
            ) / total
        else:
            closed = min(abs(old_quantity), quantity)
            direction = 1 if old_quantity > 0 else -1
            position.realized_pnl += (
                (price - position.average_price) * closed * direction
            )
            if new_quantity == 0:
                position.average_price = 0.0
            elif old_quantity * new_quantity < 0:
                position.average_price = price
        position.quantity = new_quantity

        self._fill_counter += 1
        book = self._books.get(order.instrument_id)
        self._fills.append(
            PaperFill(
                fill_id=f"FILL-{self._fill_counter:08d}",
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                side=order.side,
                quantity=quantity,
                price=price,
                fee=fee,
                sequence_number=(book.sequence_number if book is not None else None),
            )
        )

    def _mark_price(self, instrument_id: str) -> float:
        book = self._books.get(instrument_id)
        if book is None or not book.bids or not book.asks:
            return 0.0
        return (book.bids[0].price + book.asks[0].price) / 2

    def _require_order(self, order_id: str) -> PaperOrder:
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"Unknown order: {order_id}.")
        return order
