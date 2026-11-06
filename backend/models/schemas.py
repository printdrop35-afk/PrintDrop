"""Pydantic v2 request/response models. Mirrored by hand in frontend/src/lib/types.ts — keep in sync."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from lib.pricing import PAPER_SIZES

PaperSize = Literal["A4", "A3", "A5", "Letter", "Legal"]
ColorMode = Literal["bw", "color"]
OrderStatus = Literal["pending", "printing", "ready", "picked_up", "cancelled"]
PaymentStatus = Literal["unpaid", "paid_counter", "paid_online"]
TenantRole = Literal["owner", "manager", "operator"]


# ---------- pricing ----------
class ColorPrice(BaseModel):
    bw: int = Field(ge=0, le=100_00)
    color: int = Field(ge=0, le=100_00)


class Pricing(BaseModel):
    print: dict[str, ColorPrice]
    duplex_discount_pct: int = Field(ge=0, le=50)
    photocopy: ColorPrice
    scan_cents: int = Field(ge=0, le=100_00)

    @field_validator("print")
    @classmethod
    def all_sizes(cls, v: dict[str, ColorPrice]) -> dict[str, ColorPrice]:
        if set(v.keys()) != set(PAPER_SIZES):
            raise ValueError(f"Formats attendus : {', '.join(PAPER_SIZES)}")
        return v


# ---------- auth ----------
class RegisterIn(BaseModel):
    org_name: str = Field(min_length=2, max_length=80)
    shop_name: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=1, max_length=60)
    owner_name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class OrgOut(BaseModel):
    id: str
    name: str
    status: str
    plan: str


class ShopOut(BaseModel):
    id: str
    org_id: str
    slug: str
    name: str
    city: str
    address: str = ""
    accepting_orders: bool
    pricing: Pricing
    created_at: datetime


class MeOut(BaseModel):
    user: UserOut
    platform_role: str | None
    org: OrgOut | None
    role: TenantRole | None
    permissions: list[str]
    shops: list[ShopOut]


# ---------- shops ----------
class ShopCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=1, max_length=60)
    address: str = Field(default="", max_length=160)


class ShopUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    city: str | None = Field(default=None, min_length=1, max_length=60)
    address: str | None = Field(default=None, max_length=160)
    accepting_orders: bool | None = None


# ---------- customer portal ----------
class PublicShopOut(BaseModel):
    slug: str
    name: str
    city: str
    address: str
    accepting_orders: bool
    pricing: Pricing


class DocumentUploadOut(BaseModel):
    id: str
    filename: str
    kind: str
    page_count: int
    size_bytes: int
    upload_token: str


class PrintOptions(BaseModel):
    paper_size: PaperSize = "A4"
    color: ColorMode = "bw"
    duplex: bool = False
    copies: int = Field(default=1, ge=1, le=100)
    page_range: str = Field(default="", max_length=100)


class QuoteItemIn(BaseModel):
    document_id: str
    upload_token: str
    options: PrintOptions


class ServicesIn(BaseModel):
    photocopy_bw: int = Field(default=0, ge=0, le=1000)
    photocopy_color: int = Field(default=0, ge=0, le=1000)
    scan_pages: int = Field(default=0, ge=0, le=1000)


class QuoteIn(BaseModel):
    items: list[QuoteItemIn] = Field(default_factory=list, max_length=20)
    services: ServicesIn = Field(default_factory=ServicesIn)


class OrderCreateIn(QuoteIn):
    customer_name: str = Field(min_length=2, max_length=80)
    customer_phone: str = Field(min_length=6, max_length=20)
    note: str = Field(default="", max_length=500)


class QuoteLine(BaseModel):
    kind: Literal["print", "photocopy", "scan"]
    label: str
    document_id: str | None
    filename: str | None
    options: PrintOptions | None
    pages: int
    copies: int
    sheets: int
    unit_cents: int
    subtotal_cents: int


class QuoteOut(BaseModel):
    lines: list[QuoteLine]
    total_cents: int
    currency: Literal["EUR"] = "EUR"


class TrackIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)
    phone: str = Field(min_length=6, max_length=20)


class StatusEvent(BaseModel):
    status: OrderStatus
    at: datetime
    by: str


class OrderPublicOut(BaseModel):
    code: str
    shop_name: str
    shop_slug: str
    status: OrderStatus
    payment_status: PaymentStatus
    lines: list[QuoteLine]
    total_cents: int
    currency: str
    created_at: datetime
    history: list[StatusEvent]


# ---------- orders (dashboard) ----------
class OrderOut(BaseModel):
    id: str
    code: str
    shop_id: str
    shop_name: str
    customer_name: str
    customer_phone: str
    note: str
    lines: list[QuoteLine]
    total_cents: int
    currency: str
    status: OrderStatus
    payment_status: PaymentStatus
    payment_method: str | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
    history: list[StatusEvent]


class OrderStatusIn(BaseModel):
    status: OrderStatus


class OrderPayIn(BaseModel):
    method: Literal["cash", "card_terminal"]


class DownloadLinkOut(BaseModel):
    url: str
    expires_at: int


class ShopStatsOut(BaseModel):
    orders_today: int
    pending: int
    printing: int
    ready: int
    revenue_today_cents: int
    unpaid_cents: int


# ---------- staff ----------
class StaffOut(BaseModel):
    membership_id: str
    user_id: str
    name: str
    email: str
    role: TenantRole
    active: bool
    created_at: datetime


class StaffCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["manager", "operator"]


class StaffUpdateIn(BaseModel):
    role: Literal["manager", "operator"] | None = None
    active: bool | None = None


# ---------- audit ----------
class AuditOut(BaseModel):
    id: str
    at: datetime
    actor_email: str
    action: str
    resource_type: str
    resource_id: str
    outcome: str
    details: dict[str, Any]


# ---------- super-admin ----------
class AdminStatsOut(BaseModel):
    organizations: int
    active_organizations: int
    shops: int
    users: int
    orders: int
    revenue_cents: int


class AdminOrgOut(BaseModel):
    id: str
    name: str
    status: Literal["active", "suspended"]
    plan: Literal["essai", "starter", "pro"]
    owner_email: str
    shops_count: int
    orders_count: int
    revenue_cents: int
    created_at: datetime


class AdminOrgUpdateIn(BaseModel):
    status: Literal["active", "suspended"] | None = None
    plan: Literal["essai", "starter", "pro"] | None = None
