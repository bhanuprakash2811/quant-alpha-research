

import pandas as pd

from quant_alpha.data.validation import (
    validate_market_dataframe,
)


def valid_dataframe():
    return pd.DataFrame({
        "instrument_id": ["NSE_RELIANCE", "NSE_TCS"],
        "symbol": ["RELIANCE", "TCS"],
        "exchange": ["NSE", "NSE"],
        "timestamp": pd.to_datetime([
            "2026-11-20 15:30:00+05:30",
            "2026-11-20 15:30:00+05:30",
        ]),
        "open": [1450.0, 3200.0],
        "high": [1480.0, 3250.0],
        "low": [1440.0, 3180.0],
        "close": [1470.0, 3230.0],
        "volume": [250000, 150000],
        "currency": ["INR", "INR"],
    })


def test_valid_dataframe():
    report = validate_market_dataframe(valid_dataframe())

    assert report.is_valid
    assert report.total_rows == 2


def test_duplicate_instrument_timestamp():
    df = valid_dataframe()
    df.loc[1, "instrument_id"] = "NSE_RELIANCE"

    report = validate_market_dataframe(df)

    assert not report.is_valid
    assert any("duplicate" in error.lower()
               for error in report.errors)


def test_negative_volume():
    df = valid_dataframe()
    df.loc[0, "volume"] = -100

    report = validate_market_dataframe(df)

    assert not report.is_valid


def test_invalid_ohlc():
    df = valid_dataframe()
    df.loc[0, "high"] = 1400.0

    report = validate_market_dataframe(df)

    assert not report.is_valid


def test_missing_values():
    df = valid_dataframe()
    df.loc[0, "close"] = None

    report = validate_market_dataframe(df)

    assert not report.is_valid


def test_missing_column():
    df = valid_dataframe().drop(columns=["volume"])

    report = validate_market_dataframe(df)

    assert not report.is_valid
