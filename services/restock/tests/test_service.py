"""Restock rules against a real test database, with Inventory replaced by FakeInventory."""
import pytest

from app import service as shop
from app.inventory_client import InventoryUnavailable


def test_free_text_entry_defaults(conn, inventory):
    entry = shop.add_entry(conn, 2, name=" batteries ")
    assert (entry["name"], entry["unit"], entry["status"], entry["source"]) == ("batteries", "pcs", "open", "manual")
    assert entry["inventory_item_id"] is None


def test_entry_needs_name_or_item_and_positive_quantity(conn, inventory):
    with pytest.raises(shop.Conflict):
        shop.add_entry(conn, 1)
    with pytest.raises(shop.Conflict):
        shop.add_entry(conn, 0, name="bread")


def test_linked_entry_copies_name_and_unit_from_inventory(conn, inventory):
    inventory.add(7, "oat milk", unit="l")
    entry = shop.add_entry(conn, 2, inventory_item_id=7)
    assert (entry["name"], entry["unit"], entry["inventory_item_id"]) == ("oat milk", "l", 7)


def test_linked_entry_for_unknown_item_fails(conn, inventory):
    with pytest.raises(shop.NotFound):
        shop.add_entry(conn, 1, inventory_item_id=999)


def test_same_item_cannot_be_open_twice(conn, inventory):
    inventory.add(1)
    shop.add_entry(conn, 1, inventory_item_id=1)
    with pytest.raises(shop.Conflict):
        shop.add_entry(conn, 1, inventory_item_id=1)


def test_add_low_stock_items_tops_up_to_twice_the_threshold_and_is_idempotent(conn, inventory):
    inventory.add(1, "milk", quantity=1, min_threshold=2)
    inventory.add(2, "eggs", quantity=12, min_threshold=6)  # not low
    added = shop.add_low_stock_items(conn)
    assert [(e["inventory_item_id"], e["quantity"], e["source"]) for e in added] == [(1, 3, "low_stock")]
    assert shop.add_low_stock_items(conn) == []  # already on the list


def test_mark_bought_restocks_inventory(conn, inventory):
    inventory.add(1, quantity=1, min_threshold=2)
    entry = shop.add_low_stock_items(conn)[0]
    bought = shop.mark_bought(conn, entry["id"])
    assert bought["status"] == "bought" and bought["bought_at"] and bought["restocked"] is True
    assert inventory.items[1]["quantity"] == 4
    shop.add_entry(conn, 1, inventory_item_id=1)  # once bought, it can go on the list again


def test_mark_bought_free_text_does_not_call_inventory(conn, inventory):
    inventory.down = True  # would raise if called
    entry = shop.add_entry(conn, 1, name="birthday candles")
    assert shop.mark_bought(conn, entry["id"])["restocked"] is False


def test_mark_bought_when_inventory_item_was_deleted(conn, inventory):
    inventory.add(1)
    entry = shop.add_entry(conn, 1, inventory_item_id=1)
    del inventory.items[1]
    bought = shop.mark_bought(conn, entry["id"])
    assert bought["status"] == "bought" and bought["restocked"] is False


def test_mark_bought_with_inventory_down_changes_nothing(conn, inventory):
    inventory.add(1)
    entry = shop.add_entry(conn, 1, inventory_item_id=1)
    inventory.down = True
    with pytest.raises(InventoryUnavailable):
        shop.mark_bought(conn, entry["id"])
    assert shop.get_entry(conn, entry["id"])["status"] == "open"  # can simply be retried


def test_list_works_while_inventory_is_down(conn, inventory):
    inventory.add(1, "milk")
    shop.add_entry(conn, 1, inventory_item_id=1)
    inventory.down = True
    assert [e["name"] for e in shop.list_entries(conn)] == ["milk"]  # copied name, no call needed


def test_bought_entries_cannot_be_bought_or_edited_again(conn, inventory):
    entry = shop.add_entry(conn, 1, name="bread")
    shop.mark_bought(conn, entry["id"])
    with pytest.raises(shop.Conflict):
        shop.mark_bought(conn, entry["id"])
    with pytest.raises(shop.Conflict):
        shop.update_entry(conn, entry["id"], {"quantity": 2})


def test_update_entry(conn, inventory):
    entry = shop.add_entry(conn, 1, name="bread")
    updated = shop.update_entry(conn, entry["id"], {"quantity": 3, "status": "bought"})
    assert updated["quantity"] == 3 and updated["status"] == "open"  # status is not editable
    with pytest.raises(shop.Conflict):
        shop.update_entry(conn, entry["id"], {"quantity": -1})


def test_list_filters_and_orders_open_first(conn, inventory):
    bread = shop.add_entry(conn, 1, name="bread")
    shop.add_entry(conn, 1, name="rice")
    shop.mark_bought(conn, bread["id"])
    assert [e["name"] for e in shop.list_entries(conn)] == ["rice", "bread"]
    assert [e["name"] for e in shop.list_entries(conn, "bought")] == ["bread"]


def test_unknown_entry_errors(conn, inventory):
    for action in (lambda: shop.get_entry(conn, 9), lambda: shop.delete_entry(conn, 9), lambda: shop.mark_bought(conn, 9)):
        with pytest.raises(shop.NotFound):
            action()
