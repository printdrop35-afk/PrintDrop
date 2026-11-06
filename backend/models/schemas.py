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
    customer_email: EmailStr | None = None
    notify: bool = True
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
    customer_email: str | None = None
    notify: bool = True
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


# ---------- notifications ----------
class NotificationOut(BaseModel):
    id: str
    channel: Literal["email", "sms"]
    recipient: str
    status: Literal["queued", "sending", "sent", "failed", "skipped"]
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


class NotificationStatusOut(BaseModel):
    email_configured: bool
    sms_configured: bool


# ---------- print agent (dashboard side) ----------
JobStatus = Literal["queued", "claimed", "printing", "printed", "failed", "cancelled"]


class PrintJobOut(BaseModel):
    id: str
    order_id: str
    order_code: str
    line_index: int
    filename: str | None
    kind: Literal["initial", "reprint"]
    reason: str
    status: JobStatus
    printer_name: str | None
    error: str | None
    requested_by: str
    created_at: datetime
    updated_at: datetime
    printed_at: datetime | None


class ReprintIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class PairingCodeOut(BaseModel):
    code: str
    expires_at: datetime


class AgentOut(BaseModel):
    id: str
    name: str
    hostname: str
    version: str
    status: Literal["active", "revoked"]
    online: bool
    last_seen_at: datetime | None
    created_at: datetime


class PrinterOut(BaseModel):
    id: str
    agent_id: str
    name: str
    is_default: bool
    enabled: bool
    status: Literal["online", "offline", "error"]
    status_detail: str
    supports_color: bool
    online: bool
    last_seen_at: datetime | None


class PrinterUpdateIn(BaseModel):
    enabled: bool | None = None
    is_default: bool | None = None


# ---------- print agent (agent API) ----------
class AgentPairIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    name: str = Field(min_length=1, max_length=60)
    hostname: str = Field(default="", max_length=80)
    version: str = Field(default="", max_length=20)


class AgentPairOut(BaseModel):
    agent_id: str
    api_key: str
    shop_id: str
    shop_name: str


class AgentPrinterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    is_default: bool = False
    status: Literal["online", "offline", "error"] = "online"
    detail: str = Field(default="", max_length=200)
    supports_color: bool = True


class AgentHeartbeatIn(BaseModel):
    version: str = Field(default="", max_length=20)
    printers: list[AgentPrinterIn] = Field(default_factory=list, max_length=50)


class AgentHeartbeatOut(BaseModel):
    shop_name: str
    poll_seconds: int


class AgentJobOut(BaseModel):
    id: str
    lease_id: str
    order_code: str
    kind: Literal["initial", "reprint"]
    filename: str | None
    file_kind: str
    options: PrintOptions
    pages: list[int]
    printer_name: str
    download_url: str


class AgentClaimOut(BaseModel):
    jobs: list[AgentJobOut]
    message: str = ""


class AgentReportIn(BaseModel):
    lease_id: str = Field(min_length=8, max_length=64)
    status: Literal["printing", "printed", "failed", "requeue"]
    error: str = Field(default="", max_length=300)


class AgentReportOut(BaseModel):
    job_id: str
    status: JobStatus


# ---------- alerts & reports ----------
class AlertOut(BaseModel):
    kind: Literal["agent_offline", "printer_offline", "job_failed", "low_paper"]
    message: str
    since: datetime
    printer_name: str | None = None
    order_id: str | None = None
    order_code: str | None = None


class HourBucket(BaseModel):
    hour: int
    orders: int
    revenue_cents: int


class DailyReportOut(BaseModel):
    day: str
    shop_id: str
    shop_name: str
    orders_total: int
    orders_cancelled: int
    orders_picked_up: int
    revenue_cents: int
    revenue_cash_cents: int
    revenue_card_cents: int
    payments_count: int
    avg_basket_cents: int
    unpaid_cents: int
    pages_bw: int
    pages_color: int
    sheets: int
    photocopies: int
    scans: int
    jobs_printed: int
    jobs_failed: int
    busiest_hour: int | None
    hours: list[HourBucket]


class ReportSettingsIn(BaseModel):
    daily_email: bool


class ReportSettingsOut(BaseModel):
    daily_email: bool
    recipient: str


# ---------- paper stock ----------
class PaperLevelOut(BaseModel):
    paper_size: PaperSize
    stock_sheets: int
    used_sheets: int
    remaining_sheets: int
    pct_used: int
    set_at: datetime
    level: Literal["ok", "low", "out"]


class PaperStockOut(BaseModel):
    alert_pct: int
    levels: list[PaperLevelOut]


class PaperStockIn(BaseModel):
    """Sheets currently on hand per size; a value resets the count from now, null stops tracking that size."""
    stock: dict[PaperSize, int | None] = Field(default_factory=dict)
    alert_pct: int = Field(default=80, ge=10, le=100)

    @field_validator("stock")
    @classmethod
    def positive(cls, v: dict[str, int | None]) -> dict[str, int | None]:
        for size, n in v.items():
            if n is not None and not 1 <= n <= 1_000_000:
                raise ValueError(f"Stock {size} : entre 1 et 1 000 000 feuilles")
        return v
