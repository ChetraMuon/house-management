from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["manager", "admin", "emp"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth / users ----------
class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    email: str | None = None
    role: Role
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=120)
    email: str | None = None


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=72)
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = None


class UserRoleUpdate(BaseModel):
    role: Literal["admin", "emp"]


class UserActiveUpdate(BaseModel):
    is_active: bool


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=72)


# ---------- products / stock ----------
class CategoryOut(ORM):
    id: int
    name: str


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    category_id: int | None = None
    unit: str = "pcs"
    price: Decimal = Field(ge=0)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    min_stock: int = Field(default=5, ge=0)


class ProductUpdate(BaseModel):
    sku: str | None = None
    name: str | None = None
    category_id: int | None = None
    unit: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    min_stock: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductOut(ORM):
    id: int
    sku: str
    name: str
    image_url: str | None = None
    category_id: int | None
    unit: str
    price: Decimal
    cost: Decimal
    stock_qty: int
    min_stock: int
    is_active: bool
    can_delete: bool = False


class StockChange(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=255)


class StockAdjust(BaseModel):
    product_id: int
    new_quantity: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=255)


class StockMovementOut(ORM):
    id: int
    product_id: int
    movement_type: str
    quantity: int
    qty_before: int
    qty_after: int
    reference: str | None
    note: str | None
    created_by: int
    created_at: datetime


# ---------- sales ----------
class SaleItemIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class SaleCreate(BaseModel):
    customer_name: str | None = Field(default=None, max_length=120)
    customer_phone: str | None = Field(default=None, max_length=30)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    items: list[SaleItemIn] = Field(min_length=1)


class CheckoutIn(BaseModel):
    method: Literal["CASH", "CARD", "TRANSFER"] = "CASH"
    amount_received: Decimal = Field(ge=0)


class ChangeQuery(BaseModel):
    total: Decimal = Field(ge=0)
    received: Decimal = Field(ge=0)


class SaleItemOut(ORM):
    id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class PaymentOut(ORM):
    method: str
    amount_due: Decimal
    amount_received: Decimal
    change_given: Decimal
    created_at: datetime
    status: str = "SUCCEEDED"
    provider: str | None = None
    provider_txn_id: str | None = None
    provider_ref: str | None = None


class ApprovalOut(ORM):
    id: int
    sale_id: int
    status: str
    requested_by: int
    decided_by: int | None
    decision_note: str | None
    requested_at: datetime
    decided_at: datetime | None


class CustomerOut(ORM):
    id: int
    phone: str
    full_name: str | None = None
    created_at: datetime


class CustomerSaleOut(ORM):
    id: int
    receipt_no: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    created_at: datetime
    status: str
    items: list[SaleItemOut] = []


class CustomerHistoryOut(ORM):
    customer: CustomerOut
    purchases: list[CustomerSaleOut]
    total_spent: Decimal


class SaleOut(ORM):
    id: int
    receipt_no: str
    customer_id: int | None = None
    customer_name: str | None
    customer_phone: str | None = None
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    status: str
    requires_approval: bool
    created_by: int
    created_at: datetime
    paid_at: datetime | None
    items: list[SaleItemOut] = []
    payment: PaymentOut | None = None
    approval: ApprovalOut | None = None


class EmployeeOptionOut(BaseModel):
    id: int
    full_name: str
    username: str


class EmployeeSaleRowOut(BaseModel):
    id: int
    receipt_no: str
    customer_name: str | None = None
    customer_phone: str | None = None
    total: Decimal
    status: str
    created_at: datetime
    paid_at: datetime | None = None
    employee_id: int
    employee_name: str
    employee_username: str


class EmployeeSalesOut(BaseModel):
    day: date
    count: int
    paid_count: int
    total: Decimal
    sales: list[EmployeeSaleRowOut]
    employees: list[EmployeeOptionOut]


class PaywayConfigOut(BaseModel):
    payway_enabled: bool
    currency: str = "USD"
    sandbox: bool = False
    simulator_enabled: bool = False


class PaywayQrOut(BaseModel):
    sale_id: int
    tran_id: str
    qr_image: str | None = None
    qr_string: str | None = None
    deeplink: str | None = None
    amount: Decimal
    currency: str = "USD"
    expires_at: datetime
    status: str = "PENDING"
    sandbox: bool = False


class PaywayStatusOut(BaseModel):
    sale_id: int
    status: str
    sale_status: str
    message: str | None = None
    sale: SaleOut | None = None


class PaywaySimulatorSaleOut(BaseModel):
    sale_id: int
    receipt_no: str
    customer_name: str | None = None
    customer_phone: str | None = None
    total: Decimal
    currency: str = "USD"
    tran_id: str
    status: str
    expires_at: datetime | None = None
    created_at: datetime
    cashier_name: str
    expired: bool = False


class ApprovalDecision(BaseModel):
    note: str | None = Field(default=None, max_length=255)


class ApprovalRow(BaseModel):
    approval_id: int
    sale_id: int
    receipt_no: str
    total: Decimal
    requested_by: str
    requested_at: datetime
    status: str
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
