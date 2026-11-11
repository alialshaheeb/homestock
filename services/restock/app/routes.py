"""Restock HTTP API (/shopping-list). Thin layer over app/service.py."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app import service
from app.db import get_db
from app.inventory_client import InventoryUnavailable

router = APIRouter(prefix="/shopping-list", tags=["restock"])


class EntryIn(BaseModel):
    """Either a free-text `name`, or an `inventory_item_id` (name and unit are then copied)."""
    quantity: float = Field(gt=0)
    name: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    inventory_item_id: int | None = None


class EntryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=20)


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except service.Conflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InventoryUnavailable:
        # Designed failure: the list itself still works, only this action needs Inventory.
        raise HTTPException(status_code=503, detail="The inventory service is not reachable right now. Try again in a moment.")


@router.get("")
def list_entries(status: Literal["open", "bought"] | None = None, conn=Depends(get_db)):
    return service.list_entries(conn, status)


@router.post("", status_code=201)
def add_entry(body: EntryIn, conn=Depends(get_db)):
    return _call(service.add_entry, conn, body.quantity, body.name, body.unit, body.inventory_item_id)


@router.post("/from-low-stock")
def add_low_stock_items(conn=Depends(get_db)):
    """Adds every low-stock Inventory item that is not already on the list. Returns the new entries."""
    return _call(service.add_low_stock_items, conn)


@router.get("/{entry_id}")
def get_entry(entry_id: int, conn=Depends(get_db)):
    return _call(service.get_entry, conn, entry_id)


@router.patch("/{entry_id}")
def update_entry(entry_id: int, body: EntryPatch, conn=Depends(get_db)):
    return _call(service.update_entry, conn, entry_id, body.model_dump(exclude_unset=True))


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int, conn=Depends(get_db)):
    _call(service.delete_entry, conn, entry_id)
    return Response(status_code=204)


@router.post("/{entry_id}/bought")
def mark_bought(entry_id: int, conn=Depends(get_db)):
    return _call(service.mark_bought, conn, entry_id)
