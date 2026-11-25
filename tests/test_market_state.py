
from datetime import UTC, datetime, timedelta

import pytest

from quant_alpha.data.schema import (
    OrderBookSnapshot,
    OrderBookUpdate,
    PriceLevel,
    TradeEvent,
)
from quant_alpha.features.market_state import MarketStateEngine
from quant_alpha.features.microstructure.engine import (
    MicrostructureEngine,
)
from quant_alpha.features.orderflow.ofi import OFIResult
from quant_alpha.features.tradeflow.engine import (
    TradeFlowEngine,
)

BASE_TIME = datetime(2026, 11, 23, 9, 15, tzinfo=UTC)


def create_snapshot(
    instrument_id: str = "NIFTY-FUT",
    sequence_number: int = 100,
    timestamp: datetime = BASE_TIME,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        instrument_id=instrument_id,
        symbol="NIFTY",
        exchange="NSE",
        provider="TEST",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        sequence_number=sequence_number,
        bids=[
            PriceLevel(price=26000.0, quantity=500),
            PriceLevel(price=25999.0, quantity=300),
            PriceLevel(price=25998.0, quantity=200),
        ],
        asks=[
            PriceLevel(price=26001.0, quantity=200),
            PriceLevel(price=26002.0, quantity=250),
            PriceLevel(price=26003.0, quantity=150),
        ],
    )


def create_trade(
    instrument_id: str = "NIFTY-FUT",
    timestamp: datetime = BASE_TIME,
    quantity: int = 25,
    aggressor_side: str = "BUY",
) -> TradeEvent:
    return TradeEvent(
        instrument_id=instrument_id,
        symbol="NIFTY",
        exchange="NSE",
        provider="TEST",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        trade_id="TRADE-001",
        price=26000.5,
        quantity=quantity,
        aggressor_side=aggressor_side,
    )


def create_update(
    timestamp: datetime = BASE_TIME + timedelta(seconds=1),
) -> OrderBookUpdate:
    return OrderBookUpdate(
        instrument_id="NIFTY-FUT",
        symbol="NIFTY",
        exchange="NSE",
        provider="TEST",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        sequence_number=101,
        side="BID",
        action="UPSERT",
        price=26000.0,
        quantity=550,
    )


def create_trade_flow():
    engine = TradeFlowEngine("NIFTY-FUT")
    return engine.process_trade(create_trade())


def test_register_instrument() -> None:
    engine = MarketStateEngine()

    engine.register_instrument("NIFTY-FUT")

    assert engine.registered_instruments() == ("NIFTY-FUT",)


def test_register_empty_instrument_id() -> None:
    engine = MarketStateEngine()

    with pytest.raises(ValueError):
        engine.register_instrument("")


def test_register_duplicate_instrument() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    with pytest.raises(ValueError):
        engine.register_instrument("NIFTY-FUT")


def test_get_initial_market_state() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    state = engine.get_state("NIFTY-FUT")

    assert state.instrument_id == "NIFTY-FUT"
    assert state.book_snapshot is None
    assert state.trade_flow is None
    assert state.ofi is None
    assert state.microstructure is None
    assert state.book_valid is None


def test_get_state_for_unregistered_instrument() -> None:
    engine = MarketStateEngine()

    with pytest.raises(KeyError):
        engine.get_state("NIFTY-FUT")


def test_update_trade_event() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    trade = create_trade()
    trade_flow = create_trade_flow()

    state = engine.update(
        trade,
        trade_flow=trade_flow,
    )

    assert state.trade_flow is not None
    assert state.trade_flow.buy_volume == 25
    assert state.trade_flow.cumulative_volume_delta == 25

    assert state.last_trade_exchange_timestamp == trade.exchange_timestamp
    assert state.last_trade_received_timestamp == trade.received_timestamp

    assert state.last_event_exchange_timestamp == trade.exchange_timestamp
    assert state.last_event_received_timestamp == trade.received_timestamp


def test_trade_event_requires_trade_flow() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    with pytest.raises(ValueError):
        engine.update(create_trade())


def test_trade_flow_instrument_mismatch() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    wrong_engine = TradeFlowEngine("BANKNIFTY-FUT")
    wrong_trade = create_trade(instrument_id="BANKNIFTY-FUT")
    wrong_flow = wrong_engine.process_trade(wrong_trade)

    with pytest.raises(ValueError, match="Trade-flow instrument mismatch"):
        engine.update(
            create_trade(),
            trade_flow=wrong_flow,
        )


def test_update_order_book_snapshot() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    snapshot = create_snapshot()
    microstructure = MicrostructureEngine.calculate(snapshot)

    state = engine.update(
        snapshot,
        book_snapshot=snapshot,
        microstructure=microstructure,
    )

    assert state.book_snapshot == snapshot
    assert state.microstructure == microstructure
    assert state.book_valid is True

    assert state.last_book_exchange_timestamp == snapshot.exchange_timestamp
    assert state.last_book_received_timestamp == snapshot.received_timestamp


def test_order_book_event_requires_analytics() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    snapshot = create_snapshot()

    with pytest.raises(ValueError):
        engine.update(snapshot, book_snapshot=snapshot)


def test_order_book_instrument_mismatch() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    wrong_snapshot = create_snapshot(
        instrument_id="BANKNIFTY-FUT"
    )
    microstructure = MicrostructureEngine.calculate(wrong_snapshot)

    with pytest.raises(ValueError, match="Order-book instrument mismatch"):
        engine.update(
            create_snapshot(),
            book_snapshot=wrong_snapshot,
            microstructure=microstructure,
        )


def test_microstructure_instrument_mismatch() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    snapshot = create_snapshot()
    wrong_snapshot = create_snapshot(
        instrument_id="BANKNIFTY-FUT"
    )
    wrong_microstructure = MicrostructureEngine.calculate(wrong_snapshot)

    with pytest.raises(ValueError, match="Microstructure instrument mismatch"):
        engine.update(
            snapshot,
            book_snapshot=snapshot,
            microstructure=wrong_microstructure,
        )


def test_preserve_trade_flow_when_order_book_updates() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    trade = create_trade()
    trade_flow = create_trade_flow()

    engine.update(
        trade,
        trade_flow=trade_flow,
    )

    snapshot = create_snapshot()
    microstructure = MicrostructureEngine.calculate(snapshot)

    state = engine.update(
        snapshot,
        book_snapshot=snapshot,
        microstructure=microstructure,
    )

    assert state.trade_flow == trade_flow
    assert state.book_snapshot == snapshot


def test_preserve_order_book_when_trade_arrives() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    snapshot = create_snapshot()
    microstructure = MicrostructureEngine.calculate(snapshot)

    engine.update(
        snapshot,
        book_snapshot=snapshot,
        microstructure=microstructure,
    )

    trade = create_trade(
        timestamp=BASE_TIME + timedelta(seconds=1)
    )

    trade_flow = create_trade_flow()

    state = engine.update(
        trade,
        trade_flow=trade_flow,
    )

    assert state.book_snapshot == snapshot
    assert state.microstructure == microstructure
    assert state.trade_flow == trade_flow
    assert state.book_valid is True


def test_preserve_previous_ofi_when_new_snapshot_has_no_ofi() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    snapshot = create_snapshot()
    microstructure = MicrostructureEngine.calculate(snapshot)

    ofi = OFIResult(
        instrument_id="NIFTY-FUT",
        bid_component=50.0,
        ask_component=0.0,
        value=50.0,
    )

    engine.update(
        snapshot,
        book_snapshot=snapshot,
        microstructure=microstructure,
        ofi=ofi,
    )

    next_snapshot = create_snapshot(
        sequence_number=102,
        timestamp=BASE_TIME + timedelta(seconds=2),
    )

    next_microstructure = MicrostructureEngine.calculate(next_snapshot)

    state = engine.update(
        next_snapshot,
        book_snapshot=next_snapshot,
        microstructure=next_microstructure,
    )

    assert state.ofi == ofi
    assert state.book_snapshot == next_snapshot


def test_ofi_instrument_mismatch() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    snapshot = create_snapshot()
    microstructure = MicrostructureEngine.calculate(snapshot)

    wrong_ofi = OFIResult(
        instrument_id="BANKNIFTY-FUT",
        bid_component=10.0,
        ask_component=5.0,
        value=15.0,
    )

    with pytest.raises(ValueError, match="OFI instrument mismatch"):
        engine.update(
            snapshot,
            book_snapshot=snapshot,
            microstructure=microstructure,
            ofi=wrong_ofi,
        )


def test_instruments_maintain_independent_market_states() -> None:
    engine = MarketStateEngine()

    engine.register_instrument("NIFTY-FUT")
    engine.register_instrument("BANKNIFTY-FUT")

    nifty_trade = create_trade(
        instrument_id="NIFTY-FUT",
        quantity=20,
    )

    banknifty_trade = create_trade(
        instrument_id="BANKNIFTY-FUT",
        quantity=35,
        aggressor_side="SELL",
    )

    nifty_flow_engine = TradeFlowEngine("NIFTY-FUT")
    banknifty_flow_engine = TradeFlowEngine("BANKNIFTY-FUT")

    nifty_flow = nifty_flow_engine.process_trade(nifty_trade)
    banknifty_flow = banknifty_flow_engine.process_trade(banknifty_trade)

    engine.update(nifty_trade, trade_flow=nifty_flow)
    engine.update(banknifty_trade, trade_flow=banknifty_flow)

    nifty_state = engine.get_state("NIFTY-FUT")
    banknifty_state = engine.get_state("BANKNIFTY-FUT")

    assert nifty_state.trade_flow is not None
    assert banknifty_state.trade_flow is not None

    assert nifty_state.trade_flow.cumulative_volume_delta == 20
    assert banknifty_state.trade_flow.cumulative_volume_delta == -35


def test_order_book_update_event_updates_book_timestamp() -> None:
    engine = MarketStateEngine()
    engine.register_instrument("NIFTY-FUT")

    snapshot = create_snapshot()
    initial_microstructure = MicrostructureEngine.calculate(snapshot)

    engine.update(
        snapshot,
        book_snapshot=snapshot,
        microstructure=initial_microstructure,
    )

    update = create_update()
    updated_snapshot = create_snapshot(
        sequence_number=101,
        timestamp=update.exchange_timestamp,
    )

    updated_microstructure = MicrostructureEngine.calculate(
        updated_snapshot
    )

    state = engine.update(
        update,
        book_snapshot=updated_snapshot,
        microstructure=updated_microstructure,
    )

    assert state.book_snapshot == updated_snapshot
    assert state.last_book_exchange_timestamp == update.exchange_timestamp
    assert state.last_event_exchange_timestamp == update.exchange_timestamp
