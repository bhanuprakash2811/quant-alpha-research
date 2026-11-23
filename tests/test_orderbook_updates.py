
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quant_alpha.data.schema import (
    OrderBookSnapshot,
    OrderBookUpdate,
    PriceLevel,
)


@pytest.fixture
def update_data():
    timestamp = datetime(2026, 11, 23, 9, 15, tzinfo=UTC)

    return {
        "instrument_id": "NIFTY-FUT",
        "symbol": "NIFTY",
        "exchange": "NSE",
        "provider": "test",
        "exchange_timestamp": timestamp,
        "received_timestamp": timestamp,
        "sequence_number": 101,
        "side": "BID",
        "action": "UPSERT",
        "price": 26000,
        "quantity": 700,
    }


def test_valid_upsert_update(update_data):
    update = OrderBookUpdate(**update_data)

    assert update.action == "UPSERT"
    assert update.side == "BID"
    assert update.quantity == 700


def test_valid_delete_update(update_data):
    update_data["action"] = "DELETE"
    update_data["quantity"] = None

    update = OrderBookUpdate(**update_data)

    assert update.action == "DELETE"
    assert update.quantity is None


def test_upsert_requires_quantity(update_data):
    update_data["quantity"] = None

    with pytest.raises(ValidationError):
        OrderBookUpdate(**update_data)


def test_delete_rejects_quantity(update_data):
    update_data["action"] = "DELETE"

    with pytest.raises(ValidationError):
        OrderBookUpdate(**update_data)


def test_update_requires_sequence_number(update_data):
    update_data["sequence_number"] = None

    with pytest.raises(ValidationError):
        OrderBookUpdate(**update_data)


def test_negative_sequence_number_rejected(update_data):
    update_data["sequence_number"] = -1

    with pytest.raises(ValidationError):
        OrderBookUpdate(**update_data)


def test_zero_quantity_rejected(update_data):
    update_data["quantity"] = 0

    with pytest.raises(ValidationError):
        OrderBookUpdate(**update_data)


def test_invalid_side_rejected(update_data):
    update_data["side"] = "MIDDLE"

    with pytest.raises(ValidationError):
        OrderBookUpdate(**update_data)




from datetime import timedelta

from quant_alpha.features.market_depth.incremental import (
    IncrementalOrderBook,
)


@pytest.fixture
def initial_snapshot():
    timestamp = datetime(2026, 11, 23, 9, 15, tzinfo=UTC)

    return OrderBookSnapshot(
        instrument_id="NIFTY-FUT",
        symbol="NIFTY",
        exchange="NSE",
        provider="test",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        sequence_number=100,
        bids=[
            PriceLevel(price=26000, quantity=500),
            PriceLevel(price=25999, quantity=300),
            PriceLevel(price=25998, quantity=200),
        ],
        asks=[
            PriceLevel(price=26001, quantity=200),
            PriceLevel(price=26002, quantity=250),
            PriceLevel(price=26003, quantity=150),
        ],
    )


@pytest.fixture
def processor(initial_snapshot):
    engine = IncrementalOrderBook("NIFTY-FUT")
    engine.load_snapshot(initial_snapshot)
    return engine


def create_update(
    sequence_number,
    side="BID",
    action="UPSERT",
    price=26000,
    quantity=700,
):
    timestamp = datetime(
        2026, 11, 23, 9, 15, tzinfo=UTC
    ) + timedelta(seconds=sequence_number - 100)

    return OrderBookUpdate(
        instrument_id="NIFTY-FUT",
        symbol="NIFTY",
        exchange="NSE",
        provider="test",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp,
        sequence_number=sequence_number,
        side=side,
        action=action,
        price=price,
        quantity=quantity,
    )


def test_snapshot_load_initializes_processor(
    processor,
    initial_snapshot,
):
    assert processor.is_valid is True
    assert processor.last_sequence_number == 100

    snapshot = processor.get_snapshot()

    assert snapshot.bids[0].price == 26000
    assert snapshot.bids[0].quantity == 500


def test_bid_quantity_upsert(processor):
    update = create_update(101, quantity=700)

    snapshot = processor.apply_update(update)

    assert snapshot.bids[0].price == 26000
    assert snapshot.bids[0].quantity == 700
    assert processor.last_sequence_number == 101


def test_ask_quantity_upsert(processor):
    update = create_update(
        101,
        side="ASK",
        price=26001,
        quantity=600,
    )

    snapshot = processor.apply_update(update)

    assert snapshot.asks[0].price == 26001
    assert snapshot.asks[0].quantity == 600


def test_new_bid_level_is_sorted_correctly(processor):
    update = create_update(
        101,
        side="BID",
        price=26001,
        quantity=400,
    )

    snapshot = processor.apply_update(update)

    assert snapshot.bids[0].price == 26001
    assert snapshot.bids[1].price == 26000


def test_new_ask_level_is_sorted_correctly(processor):
    update = create_update(
        101,
        side="ASK",
        price=26000.5,
        quantity=300,
    )

    snapshot = processor.apply_update(update)

    assert snapshot.asks[0].price == 26000.5
    assert snapshot.asks[1].price == 26001


def test_bid_level_deletion(processor):
    update = create_update(
        101,
        action="DELETE",
        price=26000,
        quantity=None,
    )

    snapshot = processor.apply_update(update)

    assert snapshot.bids[0].price == 25999
    assert len(snapshot.bids) == 2


def test_ask_level_deletion(processor):
    update = create_update(
        101,
        side="ASK",
        action="DELETE",
        price=26001,
        quantity=None,
    )

    snapshot = processor.apply_update(update)

    assert snapshot.asks[0].price == 26002
    assert len(snapshot.asks) == 2


def test_sequence_gap_invalidates_order_book(processor):
    update = create_update(102)

    with pytest.raises(RuntimeError, match="Sequence gap"):
        processor.apply_update(update)

    assert processor.is_valid is False


def test_invalid_book_rejects_further_updates(processor):
    gap_update = create_update(102)

    with pytest.raises(RuntimeError, match="Sequence gap"):
        processor.apply_update(gap_update)

    next_update = create_update(103)

    with pytest.raises(RuntimeError, match="fresh snapshot"):
        processor.apply_update(next_update)


def test_duplicate_update_is_rejected(processor):
    first_update = create_update(101)
    processor.apply_update(first_update)

    duplicate_update = create_update(101)

    with pytest.raises(ValueError, match="Stale or duplicate"):
        processor.apply_update(duplicate_update)


def test_snapshot_recovers_invalid_order_book(
    processor,
    initial_snapshot,
):
    gap_update = create_update(102)

    with pytest.raises(RuntimeError, match="Sequence gap"):
        processor.apply_update(gap_update)

    recovery_snapshot = initial_snapshot.model_copy(
        update={
            "sequence_number": 200,
        }
    )

    processor.load_snapshot(recovery_snapshot)

    assert processor.is_valid is True
    assert processor.last_sequence_number == 200

    next_update = create_update(201, quantity=800)
    result = processor.apply_update(next_update)

    assert result.bids[0].quantity == 800
    assert processor.is_valid is True


def test_wrong_instrument_update_is_rejected(processor):
    update = create_update(101).model_copy(
        update={"instrument_id": "BANKNIFTY-FUT"}
    )

    with pytest.raises(ValueError, match="Expected NIFTY-FUT"):
        processor.apply_update(update)

    assert processor.is_valid is True


def test_missing_price_level_deletion_invalidates_book(processor):
    update = create_update(
        101,
        action="DELETE",
        price=25000,
        quantity=None,
    )

    with pytest.raises(RuntimeError, match="missing BID"):
        processor.apply_update(update)

    assert processor.is_valid is False






def test_crossed_book_update_invalidates_order_book(
    processor,
):
    update = create_update(
        sequence_number=101,
        side="ASK",
        action="UPSERT",
        price=25999,
        quantity=100,
    )

    with pytest.raises(RuntimeError, match="Crossed order book"):
        processor.apply_update(update)

    assert processor.is_valid is False


def test_failed_update_does_not_modify_original_book(
    processor,
):
    original_snapshot = processor.get_snapshot()

    update = create_update(
        sequence_number=101,
        side="ASK",
        action="UPSERT",
        price=25999,
        quantity=100,
    )

    with pytest.raises(RuntimeError):
        processor.apply_update(update)

    # Internal state must remain unchanged.
    assert processor._bids == {
        level.price: level.quantity
        for level in original_snapshot.bids
    }

    assert processor._asks == {
        level.price: level.quantity
        for level in original_snapshot.asks
    }


def test_failed_update_does_not_advance_sequence(
    processor,
):
    original_sequence = processor.last_sequence_number

    update = create_update(
        sequence_number=101,
        side="ASK",
        action="UPSERT",
        price=25999,
        quantity=100,
    )

    with pytest.raises(RuntimeError):
        processor.apply_update(update)

    assert processor.last_sequence_number == original_sequence


def test_fresh_snapshot_recovers_after_crossed_book(
    processor,
    initial_snapshot,
):
    update = create_update(
        sequence_number=101,
        side="ASK",
        action="UPSERT",
        price=25999,
        quantity=100,
    )

    with pytest.raises(RuntimeError):
        processor.apply_update(update)

    processor.load_snapshot(initial_snapshot)

    assert processor.is_valid is True
    assert processor.last_sequence_number == 100
    assert processor.invalid_reason is None

