"""Inventory HTTP API. Thin layer: validate input, call service.py, map errors to status codes."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.db import get_db
from app import service

router = APIRouter(tags=["inventory"])


class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    location_id: int
    quantity: float = Field(default=0, ge=0)
    unit: str = Field(default="pcs", min_length=1, max_length=20)
    min_threshold: float = Field(default=0, ge=0)
    expiry_date: date | None = None


class ItemPatch(BaseModel):
    """Every field optional: only the fields sent are changed."""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    location_id: int | None = None
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    min_threshold: float | None = Field(default=None, ge=0)
    expiry_date: date | None = None


class StockChange(BaseModel):
    amount: float = Field(gt=0)


# ---------- response shapes (also what openapi.yaml documents) ----------

class Location(BaseModel):
    id: int
    name: str


class Item(BaseModel):
    id: int
    name: str
    location_id: int
    location: str = Field(description="Name of the location")
    quantity: float
    unit: str
    min_threshold: float
    expiry_date: date | None
    created_at: datetime
    updated_at: datetime = Field(description="Last change to the item or its stock (migration 002)")
    low_stock: bool = Field(description="min_threshold > 0 and quantity <= min_threshold")


class Message(BaseModel):
    detail: str


NOT_FOUND = {404: {"model": Message, "description": "No location or item with that id"}}
CONFLICT = {409: {"model": Message, "description": "Breaks a rule (duplicate name, not enough in stock)"}}


def _call(fn, *args, **kwargs):
    """Run a service function and turn domain errors into HTTP errors."""
    try:
        return fn(*args, **kwargs)
    except service.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except service.Conflict as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/locations", response_model=list[Location])
def list_locations(conn=Depends(get_db)):
    return service.list_locations(conn)


@router.post("/locations", status_code=201, response_model=Location, responses=CONFLICT)
def create_location(body: LocationIn, conn=Depends(get_db)):
    return _call(service.create_location, conn, body.name)


@router.get("/items", response_model=list[Item])
def list_items(
    location_id: int | None = None,
    low_stock: bool = False,
    expiring_within_days: int | None = Query(default=None, ge=0),
    conn=Depends(get_db),
):
    return service.list_items(conn, location_id, low_stock, expiring_within_days)


@router.post("/items", status_code=201, response_model=Item, responses=NOT_FOUND)
def create_item(body: ItemIn, conn=Depends(get_db)):
    return _call(service.create_item, conn, body.model_dump())


@router.get("/items/{item_id}", response_model=Item, responses=NOT_FOUND)
def get_item(item_id: int, conn=Depends(get_db)):
    return _call(service.get_item, conn, item_id)


@router.patch("/items/{item_id}", response_model=Item, responses=NOT_FOUND)
def update_item(item_id: int, body: ItemPatch, conn=Depends(get_db)):
    # exclude_unset: a field the client did not send is left alone, but an explicit
    # "expiry_date": null clears the date.
    return _call(service.update_item, conn, item_id, body.model_dump(exclude_unset=True))


@router.delete("/items/{item_id}", status_code=204, responses=NOT_FOUND)
def delete_item(item_id: int, conn=Depends(get_db)):
    _call(service.delete_item, conn, item_id)
    return Response(status_code=204)


@router.post("/items/{item_id}/consume", response_model=Item, responses={**NOT_FOUND, **CONFLICT})
def consume(item_id: int, body: StockChange, conn=Depends(get_db)):
    return _call(service.consume, conn, item_id, body.amount)


@router.post("/items/{item_id}/restock", response_model=Item, responses=NOT_FOUND)
def restock(item_id: int, body: StockChange, conn=Depends(get_db)):
    return _call(service.restock, conn, item_id, body.amount)
