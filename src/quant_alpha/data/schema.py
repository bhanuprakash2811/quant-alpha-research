
from datetime import datetime
from math import isfinite
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class MarketBar(BaseModel):
    """
    Represents one OHLCV market data observation
    for a particular financial instrument.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    instrument_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    exchange: Literal["NSE", "NYSE", "NASDAQ"]
    timestamp: datetime

    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)

    volume: int = Field(ge=0)
    currency: Literal["INR", "USD"]

    @model_validator(mode="after")
    def validate_market_bar(self):
        prices = [self.open, self.high, self.low, self.close]

        if not all(isfinite(price) for price in prices):
            raise ValueError("Prices must be finite numbers.")

        if self.high < max(self.open, self.close):
            raise ValueError(
                "High cannot be lower than open or close."
            )

        if self.low > min(self.open, self.close):
            raise ValueError(
                "Low cannot be higher than open or close."
            )

        if self.high < self.low:
            raise ValueError("High cannot be lower than low.")

        if self.timestamp.tzinfo is None:
            raise ValueError(
                "Timestamp must contain timezone information."
            )

        if self.timestamp.utcoffset() is None:
            raise ValueError(
                "Timestamp must have a valid UTC offset."
            )

        expected_currency = {
            "NSE": "INR",
            "NYSE": "USD",
            "NASDAQ": "USD",
        }

        if self.currency != expected_currency[self.exchange]:
            raise ValueError(
                f"{self.exchange} requires "
                f"{expected_currency[self.exchange]} currency."
            )

        return self


class MarketEvent(BaseModel):
    """
    Common metadata shared by streaming market events.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    instrument_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    exchange: Literal["NSE", "NYSE", "NASDAQ"]

    provider: str = Field(min_length=1)

    exchange_timestamp: datetime
    received_timestamp: datetime

    sequence_number: int | None = Field(default=None, ge=0)

    @field_validator("exchange_timestamp", "received_timestamp")
    @classmethod
    def validate_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware.")

        return value


class TradeEvent(MarketEvent):
    """
    Represents one executed trade.
    """

    event_type: Literal["TRADE"] = "TRADE"

    trade_id: str | None = None

    price: float = Field(gt=0)
    quantity: int = Field(gt=0)

    aggressor_side: Literal["BUY", "SELL", "UNKNOWN"] = "UNKNOWN"

    @field_validator("price")
    @classmethod
    def validate_finite_price(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Trade price must be finite.")

        return value


class PriceLevel(BaseModel):
    """
    Represents price and available quantity at one book level.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    price: float = Field(gt=0)
    quantity: int = Field(gt=0)

    @field_validator("price")
    @classmethod
    def validate_finite_price(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Price must be finite.")

        return value


class OrderBookSnapshot(MarketEvent):
    """
    Represents a snapshot of bid and ask market depth.

    Bids must be ordered from highest to lowest price.
    Asks must be ordered from lowest to highest price.
    """

    event_type: Literal["ORDER_BOOK_SNAPSHOT"] = "ORDER_BOOK_SNAPSHOT"

    bids: list[PriceLevel]
    asks: list[PriceLevel]

    @model_validator(mode="after")
    def validate_order_book(self):
        bid_prices = [level.price for level in self.bids]
        ask_prices = [level.price for level in self.asks]

        if bid_prices != sorted(bid_prices, reverse=True):
            raise ValueError(
                "Bid levels must be ordered from highest to lowest price."
            )

        if ask_prices != sorted(ask_prices):
            raise ValueError(
                "Ask levels must be ordered from lowest to highest price."
            )

        if len(bid_prices) != len(set(bid_prices)):
            raise ValueError("Duplicate bid price levels are not allowed.")

        if len(ask_prices) != len(set(ask_prices)):
            raise ValueError("Duplicate ask price levels are not allowed.")

        return self


class OrderBookUpdate(MarketEvent):
    """
    Normalized incremental Level 2 order-book update.

    UPSERT: Set a price level to an absolute quantity.
    DELETE: Remove the specified price level.
    """

    event_type: Literal["ORDER_BOOK_UPDATE"] = "ORDER_BOOK_UPDATE"

    side: Literal["BID", "ASK"]

    action: Literal["UPSERT", "DELETE"]

    price: float = Field(gt=0)

    quantity: int | None = Field(default=None, gt=0)

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Price must be finite.")
        return value

    @model_validator(mode="after")
    def validate_update(self):
        if self.sequence_number is None:
            raise ValueError(
                "Order book updates require a sequence number."
            )

        if self.sequence_number < 0:
            raise ValueError("Sequence number cannot be negative.")

        if self.action == "UPSERT" and self.quantity is None:
            raise ValueError(
                "UPSERT updates require a positive quantity."
            )

        if self.action == "DELETE" and self.quantity is not None:
            raise ValueError(
                "DELETE updates must not contain a quantity."
            )

        return self
