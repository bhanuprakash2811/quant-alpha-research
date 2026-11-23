
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from quant_alpha.data.schema import MarketBar


def valid_market_bar():
    return {
        "instrument_id": "NSE_RELIANCE",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "timestamp": datetime(
            2026, 11, 20, 15, 30,
            tzinfo=ZoneInfo("Asia/Kolkata"),
        ),
        "open": 1450.0,
        "high": 1480.0,
        "low": 1440.0,
        "close": 1470.0,
        "volume": 250000,
        "currency": "INR",
    }


def test_valid_market_bar():
    bar = MarketBar(**valid_market_bar())

    assert bar.symbol == "RELIANCE"
    assert bar.exchange == "NSE"
    assert bar.close == 1470.0


def test_invalid_high_price():
    data = valid_market_bar()
    data["high"] = 1400.0

    with pytest.raises(ValidationError):
        MarketBar(**data)


def test_negative_volume():
    data = valid_market_bar()
    data["volume"] = -100

    with pytest.raises(ValidationError):
        MarketBar(**data)


def test_timezone_naive_timestamp():
    data = valid_market_bar()
    data["timestamp"] = datetime(2026, 11, 20, 15, 30)

    with pytest.raises(ValidationError):
        MarketBar(**data)


def test_exchange_currency_mismatch():
    data = valid_market_bar()
    data["currency"] = "USD"

    with pytest.raises(ValidationError):
        MarketBar(**data)
