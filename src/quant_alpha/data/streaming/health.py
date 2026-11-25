"""Freshness and delivery-latency monitoring for market data feeds."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from quant_alpha.data.streaming.event_bus import MarketDataEvent


class FeedHealth(str, Enum):
    """Current health classification for one provider/instrument stream."""

    NO_DATA = "no_data"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    CLOCK_SKEW = "clock_skew"


@dataclass(frozen=True)
class FeedHealthSnapshot:
    """Point-in-time freshness metrics for a provider/instrument stream."""

    provider: str
    instrument_id: str
    status: FeedHealth
    last_exchange_timestamp: datetime | None = None
    last_received_timestamp: datetime | None = None
    last_sequence_number: int | None = None
    age: timedelta | None = None
    transport_latency: timedelta | None = None


@dataclass(frozen=True)
class _FeedObservation:
    exchange_timestamp: datetime
    received_timestamp: datetime
    sequence_number: int | None


class MarketDataFeedMonitor:
    """Track successful event freshness by provider and instrument.

    Health is computed when queried, so a stream becomes stale even if no
    background monitor is running. ``now`` can be supplied to make reads
    deterministic or to use a shared application clock.
    """

    def __init__(
        self,
        *,
        stale_after: timedelta = timedelta(seconds=5),
        degraded_latency_after: timedelta = timedelta(seconds=1),
    ) -> None:
        if stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive.")
        if degraded_latency_after <= timedelta(0):
            raise ValueError("degraded_latency_after must be positive.")

        self._stale_after = stale_after
        self._degraded_latency_after = degraded_latency_after
        self._observations: dict[tuple[str, str], _FeedObservation] = {}

    def record_event(self, event: MarketDataEvent) -> None:
        """Record an event after the consumer has processed it successfully."""

        key = (event.provider, event.instrument_id)
        previous = self._observations.get(key)

        # Keep the latest received observation if queued events arrive with
        # older timestamps; this prevents freshness from moving backwards.
        if (
            previous is not None
            and event.received_timestamp < previous.received_timestamp
        ):
            return

        self._observations[key] = _FeedObservation(
            exchange_timestamp=event.exchange_timestamp,
            received_timestamp=event.received_timestamp,
            sequence_number=event.sequence_number,
        )

    def get_health(
        self,
        provider: str,
        instrument_id: str,
        *,
        now: datetime | None = None,
    ) -> FeedHealthSnapshot:
        """Return the current health and timing metrics for one stream."""

        observed = self._observations.get((provider, instrument_id))
        if observed is None:
            return FeedHealthSnapshot(
                provider=provider,
                instrument_id=instrument_id,
                status=FeedHealth.NO_DATA,
            )

        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("now must be timezone-aware.")

        age = current_time - observed.received_timestamp
        latency = observed.received_timestamp - observed.exchange_timestamp

        if age < timedelta(0) or latency < timedelta(0):
            status = FeedHealth.CLOCK_SKEW
        elif age > self._stale_after:
            status = FeedHealth.STALE
        elif latency > self._degraded_latency_after:
            status = FeedHealth.DEGRADED
        else:
            status = FeedHealth.HEALTHY

        return FeedHealthSnapshot(
            provider=provider,
            instrument_id=instrument_id,
            status=status,
            last_exchange_timestamp=observed.exchange_timestamp,
            last_received_timestamp=observed.received_timestamp,
            last_sequence_number=observed.sequence_number,
            age=age,
            transport_latency=latency,
        )
