"""Restock rules, tested against a real Inventory on the same temp database (no mocks)."""
import pytest

from inventory import service as inv
from restock import service as shop


def add_item(conn, name="milk", **extra):
    fridge = next(loc["id"] for loc in inv.list_locations(conn) if loc["name"] == "fridge")
    return inv.create_item(conn, {"name": name, "location_id": fridge, **extra})


def test_free_text_entry_defaults(conn):
    entry = shop.add_entry(conn, 2, name=" batteries ")
    assert (entry["name"], entry["unit"], entry["status"], entry["source"]) == ("batteries", "pcs", "open", "manual")
    assert entry["inventory_item_id"] is None


def test_entry_needs_name_or_item_and_positive_quantity(conn):
    with pytest.raises(shop.Conflict):
        shop.add_entry(conn, 1)
    with pytest.raises(shop.Conflict):
        shop.add_entry(conn, 0, name="bread")


def test_linked_entry_copies_name_and_unit_from_inventory(conn):
    item = add_item(conn, "oat milk", unit="l")
    entry = shop.add_entry(conn, 2, inventory_item_id=item["id"])
    assert (entry["name"], entry["unit"], entry["inventory_item_id"]) == ("oat milk", "l", item["id"])


def test_linked_entry_for_unknown_item_fails(conn):
    with pytest.raises(shop.NotFound):
        shop.add_entry(conn, 1, inventory_item_id=999)


def test_same_item_cannot_be_open_twice(conn):
    item = add_item(conn)
    shop.add_entry(conn, 1, inventory_item_id=item["id"])
    with pytest.raises(shop.Conflict):
        shop.add_entry(conn, 1, inventory_item_id=item["id"])


def test_add_low_stock_items_tops_up_to_twice_the_threshold_and_is_idempotent(conn):
    milk = add_item(conn, "milk", quantity=1, min_threshold=2)
    add_item(conn, "eggs", quantity=12, min_threshold=6)  # not low
    added = shop.add_low_stock_items(conn)
    assert [(e["inventory_item_id"], e["quantity"], e["source"]) for e in added] == [(milk["id"], 3, "low_stock")]
    assert shop.add_low_stock_items(conn) == []  # already on the list


def test_mark_bought_restocks_inventory(conn):
    milk = add_item(conn, quantity=1, min_threshold=2)
    entry = shop.add_low_stock_items(conn)[0]
    bought = shop.mark_bought(conn, entry["id"])
    assert bought["status"] == "bought" and bought["bought_at"] and bought["restocked"] is True
    assert inv.get_item(conn, milk["id"])["quantity"] == 4
    # Once bought, the item can go on the list again.
    shop.add_entry(conn, 1, inventory_item_id=milk["id"])


def test_mark_bought_free_text_does_not_touch_inventory(conn):
    entry = shop.add_entry(conn, 1, name="birthday candles")
    assert shop.mark_bought(conn, entry["id"])["restocked"] is False


def test_mark_bought_when_inventory_item_was_deleted(conn):
    item = add_item(conn)
    entry = shop.add_entry(conn, 1, inventory_item_id=item["id"])
    inv.delete_item(conn, item["id"])
    bought = shop.mark_bought(conn, entry["id"])
    assert bought["status"] == "bought" and bought["restocked"] is False


def test_bought_entries_cannot_be_bought_or_edited_again(conn):
    entry = shop.add_entry(conn, 1, name="bread")
    shop.mark_bought(conn, entry["id"])
    with pytest.raises(shop.Conflict):
        shop.mark_bought(conn, entry["id"])
    with pytest.raises(shop.Conflict):
        shop.update_entry(conn, entry["id"], {"quantity": 2})


def test_update_entry(conn):
    entry = shop.add_entry(conn, 1, name="bread")
    updated = shop.update_entry(conn, entry["id"], {"quantity": 3, "status": "bought"})
    assert updated["quantity"] == 3 and updated["status"] == "open"  # status is not editable
    with pytest.raises(shop.Conflict):
        shop.update_entry(conn, entry["id"], {"quantity": -1})


def test_list_filters_and_orders_open_first(conn):
    bread = shop.add_entry(conn, 1, name="bread")
    shop.add_entry(conn, 1, name="rice")
    shop.mark_bought(conn, bread["id"])
    assert [e["name"] for e in shop.list_entries(conn)] == ["rice", "bread"]
    assert [e["name"] for e in shop.list_entries(conn, "bought")] == ["bread"]


def test_unknown_entry_errors(conn):
    for action in (lambda: shop.get_entry(conn, 9), lambda: shop.delete_entry(conn, 9), lambda: shop.mark_bought(conn, 9)):
        with pytest.raises(shop.NotFound):
            action()
