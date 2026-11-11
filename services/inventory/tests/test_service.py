from datetime import date

import pytest

from app import service as inv


def fridge_id(conn):
    return next(loc["id"] for loc in inv.list_locations(conn) if loc["name"] == "fridge")


def add(conn, name="milk", **extra):
    return inv.create_item(conn, {"name": name, "location_id": fridge_id(conn), **extra})


def test_create_location_normalises_and_rejects_duplicates(conn):
    assert inv.create_location(conn, "  Freezer ")["name"] == "freezer"
    with pytest.raises(inv.Conflict):
        inv.create_location(conn, "freezer")


def test_create_item_returns_location_name_and_defaults(conn):
    item = add(conn)
    assert item["location"] == "fridge"
    assert (item["quantity"], item["unit"], item["min_threshold"]) == (0, "pcs", 0)
    assert item["low_stock"] is False  # no threshold set, so never "low"


def test_create_item_in_unknown_location_fails(conn):
    with pytest.raises(inv.NotFound):
        inv.create_item(conn, {"name": "milk", "location_id": 999})


def test_low_stock_flag_and_filter(conn):
    add(conn, "milk", quantity=1, min_threshold=2)
    add(conn, "eggs", quantity=12, min_threshold=6)
    low = inv.list_items(conn, low_stock=True)
    assert [i["name"] for i in low] == ["milk"]
    assert low[0]["low_stock"] is True


def test_expiring_filter_uses_today_and_skips_items_without_expiry(conn):
    add(conn, "yogurt", expiry_date=date(2026, 11, 12))
    add(conn, "cheese", expiry_date=date(2026, 12, 30))
    add(conn, "salt")
    soon = inv.list_items(conn, expiring_within_days=3, today=date(2026, 11, 10))
    assert [i["name"] for i in soon] == ["yogurt"]


def test_filter_by_location(conn):
    add(conn, "milk")
    pantry = next(loc["id"] for loc in inv.list_locations(conn) if loc["name"] == "pantry")
    inv.create_item(conn, {"name": "rice", "location_id": pantry})
    assert [i["name"] for i in inv.list_items(conn, location_id=pantry)] == ["rice"]


def test_update_item_changes_only_allowed_fields(conn):
    item = add(conn)
    updated = inv.update_item(conn, item["id"], {"quantity": 3, "id": 999, "created_at": "x"})
    assert updated["quantity"] == 3 and updated["id"] == item["id"]
    assert updated["created_at"] == item["created_at"]


def test_update_item_to_unknown_location_fails(conn):
    item = add(conn)
    with pytest.raises(inv.NotFound):
        inv.update_item(conn, item["id"], {"location_id": 999})


def test_update_and_delete_unknown_item_fail(conn):
    with pytest.raises(inv.NotFound):
        inv.update_item(conn, 42, {"quantity": 1})
    with pytest.raises(inv.NotFound):
        inv.delete_item(conn, 42)


def test_delete_item(conn):
    item = add(conn)
    inv.delete_item(conn, item["id"])
    with pytest.raises(inv.NotFound):
        inv.get_item(conn, item["id"])


def test_consume_reduces_stock_but_never_below_zero(conn):
    item = add(conn, quantity=2)
    assert inv.consume(conn, item["id"], 1.5)["quantity"] == 0.5
    with pytest.raises(inv.Conflict):
        inv.consume(conn, item["id"], 1)
    assert inv.get_item(conn, item["id"])["quantity"] == 0.5  # failed consume changed nothing


def test_restock_adds_stock(conn):
    item = add(conn, quantity=1, min_threshold=2)
    after = inv.restock(conn, item["id"], 3)
    assert after["quantity"] == 4 and after["low_stock"] is False


@pytest.mark.parametrize("change", [inv.consume, inv.restock])
def test_stock_changes_need_a_positive_amount(conn, change):
    item = add(conn, quantity=1)
    with pytest.raises(inv.Conflict):
        change(conn, item["id"], 0)
