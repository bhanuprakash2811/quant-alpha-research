
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {
    "instrument_id",
    "symbol",
    "exchange",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "currency",
}

EXPECTED_CURRENCY = {
    "NSE": "INR",
    "NYSE": "USD",
    "NASDAQ": "USD",
}


@dataclass
class ValidationReport:
    total_rows: int
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        status = "VALID" if self.is_valid else "INVALID"

        return (
            f"Dataset status: {status}\n"
            f"Total rows: {self.total_rows}\n"
            f"Errors found: {len(self.errors)}"
        )


def validate_market_dataframe(
    df: pd.DataFrame,
) -> ValidationReport:

    report = ValidationReport(total_rows=len(df))

    # 1. Check required columns.
    missing_columns = REQUIRED_COLUMNS.difference(df.columns)

    if missing_columns:
        report.errors.append(
            f"Missing columns: {sorted(missing_columns)}"
        )
        return report

    # 2. Check missing values.
    missing_counts = df[list(REQUIRED_COLUMNS)].isna().sum()

    for column, count in missing_counts.items():
        if count > 0:
            report.errors.append(
                f"{column} contains {count} missing values."
            )

    # Stop checks that depend on missing values.
    if df[list(REQUIRED_COLUMNS)].isna().any().any():
        return report

    # 3. Check duplicate instrument/timestamp combinations.
    duplicates = df.duplicated(
        subset=["instrument_id", "timestamp"],
        keep=False,
    )

    if duplicates.any():
        report.errors.append(
            f"Found {duplicates.sum()} rows involved in "
            "duplicate instrument/timestamp combinations."
        )

    # 4. Validate numeric columns.
    price_columns = ["open", "high", "low", "close"]

    for column in price_columns:
        values = pd.to_numeric(df[column], errors="coerce")

        if not np.isfinite(values).all():
            report.errors.append(
                f"{column} contains non-finite or non-numeric values."
            )
        elif (values <= 0).any():
            report.errors.append(
                f"{column} contains non-positive prices."
            )

    volume = pd.to_numeric(df["volume"], errors="coerce")

    if not np.isfinite(volume).all():
        report.errors.append(
            "Volume contains non-finite or non-numeric values."
        )
    elif (volume < 0).any():
        report.errors.append(
            "Volume contains negative values."
        )
    elif (volume % 1 != 0).any():
        report.errors.append(
            "Volume must contain whole numbers."
        )

    # 5. Validate OHLC relationships.
    numeric_prices = df[price_columns].apply(
        pd.to_numeric, errors="coerce"
    )

    if numeric_prices.notna().all().all():
        invalid_high = (
            numeric_prices["high"]
            < numeric_prices[["open", "close"]].max(axis=1)
        )

        invalid_low = (
            numeric_prices["low"]
            > numeric_prices[["open", "close"]].min(axis=1)
        )

        invalid_range = (
            numeric_prices["high"] < numeric_prices["low"]
        )

        if invalid_high.any():
            report.errors.append(
                f"Invalid high price in {invalid_high.sum()} rows."
            )

        if invalid_low.any():
            report.errors.append(
                f"Invalid low price in {invalid_low.sum()} rows."
            )

        if invalid_range.any():
            report.errors.append(
                f"High below low in {invalid_range.sum()} rows."
            )

    # 6. Validate timezone-aware timestamps.
    timestamps = pd.to_datetime(
        df["timestamp"], errors="coerce"
    )

    if timestamps.isna().any():
        report.errors.append(
            "Timestamps contain invalid date/time values."
        )
    elif not isinstance(
        timestamps.dtype, pd.DatetimeTZDtype
    ):
        report.errors.append(
            "Timestamps must be timezone-aware."
        )

    # 7. Validate exchange/currency combinations.
    expected = df["exchange"].map(EXPECTED_CURRENCY)

    unknown_exchanges = expected.isna()

    if unknown_exchanges.any():
        report.errors.append(
            "Dataset contains unsupported exchanges."
        )

    mismatch = (
        expected.notna()
        & (df["currency"] != expected)
    )

    if mismatch.any():
        report.errors.append(
            f"Exchange/currency mismatch in {mismatch.sum()} rows."
        )

    return report
