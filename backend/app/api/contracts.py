"""Public write contracts. All monetary amounts are integer minor units."""

from typing import Annotated, Literal
from decimal import Decimal
from datetime import date
from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(min_length=1, max_length=100)]
Money = Annotated[int, Field(strict=True, ge=0, le=100_000_000_000)]
Quantity = Annotated[
    Decimal, Field(gt=0, le=1_000_000, max_digits=12, decimal_places=3)
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Contract):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    model_config = ConfigDict(extra="forbid")  # Password whitespace is significant.


class ProductFields(Contract):
    expiry_required: bool = False
    generic_name: str = Field(default="", max_length=150)
    strength: str = Field(default="", max_length=80)
    prescription_required: bool = False
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(default="", max_length=80)
    category_id: str | None = None
    unit_id: str | None = None
    search_aliases: str = Field(default="", max_length=500)
    barcode: str = Field(default="", max_length=60)
    price: Money
    cost: Money = 0
    reorder: Decimal = Field(
        default=Decimal(5), ge=0, le=1_000_000_000, decimal_places=3
    )


class ProductCreate(ProductFields):
    sku: str = Field(min_length=1, max_length=50)
    initial: Decimal = Field(
        default=Decimal(0), ge=0, le=1_000_000_000, decimal_places=3
    )


class ProductUpdate(ProductFields):
    active: bool = Field(default=True, strict=True)


class Adjustment(Contract):
    lot: str = Field(default="", max_length=80)
    expires: date | None = None
    batch_id: str | None = None
    reason_id: str | None = None
    request: Identifier
    product: Identifier
    type: Literal["IN", "OUT"]
    quantity: Quantity
    notes: str = Field(min_length=1, max_length=500)


class SaleLine(Contract):
    id: Identifier
    quantity: Quantity


class Checkout(Contract):
    held_bill_id: str | None = None
    prescription_reference: str = Field(default="", max_length=150)
    customer_id: str | None = None
    paid_now: Money | None = None
    due_date: str | None = None
    payment_method_id: str | None = None
    request: Identifier
    items: list[SaleLine] = Field(min_length=1, max_length=100)
    customer: str = Field(default="Walk-in customer", max_length=150)
    payment: Literal["cash", "external"]
    expected: Money
    tendered: Money = 0
    discount: Money = 0
    tax_bps: int = Field(default=0, strict=True, ge=0, le=10000)


class ReturnSale(Contract):
    reason: str = Field(min_length=1, max_length=500)


class SupplierCreate(Contract):
    name: str = Field(min_length=1, max_length=150)
    contact: str = Field(default="", max_length=250)
    lead_days: int = Field(default=7, strict=True, ge=0, le=365)


class PurchaseLine(Contract):
    product: Identifier
    quantity: Quantity
    unit_cost: Money


class PurchaseCreate(Contract):
    request: Identifier
    supplier: Identifier
    reference: str = Field(default="", max_length=150)
    lines: list[PurchaseLine] = Field(min_length=1, max_length=100)


class ReceiveLine(Contract):
    lot: str = Field(default="", max_length=80)
    expires: date | None = None
    product: Identifier
    quantity: Quantity


class ReceivePurchase(Contract):
    request: Identifier
    lines: list[ReceiveLine] = Field(min_length=1, max_length=100)
