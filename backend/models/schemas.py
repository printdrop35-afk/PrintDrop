"""Pydantic v2 request/response models. Mirrored by hand in frontend/src/lib/types.ts — keep in sync."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from lib.pricing import PAPER_SIZES

PaperSize = Literal["A4", "A3", "A5", "Letter", "Legal"]
ColorMode = Literal["bw", "color"]
OrderStatus = Literal["pending", "printing", "ready", "picked_up", "delivered", "cancelled"]  # delivered = digital scan downloaded
PaymentStatus = Literal["unpaid", "paid_counter", "paid_online"]
TenantRole = Literal["owner", "manager", "operator"]


# ---------- pricing ----------
class ColorPrice(BaseModel):
    bw: int = Field(ge=0, le=100_00)
    color: int = Field(ge=0, le=100_00)
    active: bool = True


class ServiceItem(BaseModel):
    id: str = Field(default="", max_length=32)
    name: str = Field(min_length=2, max_length=60)
    category: Literal["typing", "binding", "lamination", "custom"]
    unit: Literal["page", "unit", "document"]
    price_cents: int = Field(ge=0, le=1000_00)
    price_from: bool = False
    description: str = Field(default="", max_length=160)
    active: bool = True


class PricingRule(BaseModel):
    id: str = Field(default="", max_length=32)
    name: str = Field(min_length=2, max_length=60)
    min_pages: int = Field(ge=1, le=100_000)
    discount_pct: int = Field(ge=1, le=90)
    active: bool = True


class Discount(BaseModel):
    id: str = Field(default="", max_length=32)
    name: str = Field(min_length=2, max_length=60)
    code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,20}$")
    kind: Literal["percent", "fixed"]
    value: int = Field(ge=1, le=1000_00)
    min_order_cents: int = Field(default=0, ge=0, le=10_000_00)
    active: bool = True

    @field_validator("code")
    @classmethod
    def upper(cls, v: str | None) -> str | None:
        return v.upper() if v else None


class Pricing(BaseModel):
    print: dict[str, ColorPrice]
    duplex_discount_pct: int = Field(ge=0, le=50)
    photocopy: ColorPrice
    scan_cents: int = Field(ge=0, le=100_00)  # scan N&B per page
    scan_color_cents: int | None = Field(default=None, ge=0, le=100_00)  # scan couleur per page (None = same as N&B)
    min_order_cents: int = Field(default=0, ge=0, le=1000_00)
    services: list[ServiceItem] = Field(default_factory=list, max_length=50)
    rules: list[PricingRule] = Field(default_factory=list, max_length=20)
    discounts: list[Discount] = Field(default_factory=list, max_length=20)

    @field_validator("discounts")
    @classmethod
    def check_discounts(cls, v: list[Discount]) -> list[Discount]:
        codes = [d.code for d in v if d.code]
        if len(codes) != len(set(codes)):
            raise ValueError("Chaque code promo doit être unique")
        for d in v:
            if d.kind == "percent" and d.value > 90:
                raise ValueError(f"{d.name} : remise en % limitée à 90 %")
        return v

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


class SubscriptionOut(BaseModel):
    plan_code: str
    plan_name: str
    period: Literal["monthly", "yearly"]
    status: Literal["trialing", "active", "past_due", "expired", "canceled"]
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    granted_by_admin: bool = False
    days_left: int | None = None


class OrgOut(BaseModel):
    id: str
    name: str
    status: str
    plan: str
    subscription: SubscriptionOut | None = None


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
class AutoDiscountOut(BaseModel):
    name: str
    kind: Literal["percent", "fixed"]
    value: int
    min_order_cents: int


class PublicPricing(BaseModel):
    print: dict[str, ColorPrice]
    duplex_discount_pct: int
    photocopy: ColorPrice
    scan_cents: int
    scan_color_cents: int | None = None
    min_order_cents: int
    services: list[ServiceItem]
    rules: list[PricingRule]
    auto_discounts: list[AutoDiscountOut]
    has_promo_codes: bool
    vat_rate_bp: int


class PublicShopOut(BaseModel):
    slug: str
    name: str
    city: str
    address: str
    accepting_orders: bool
    pricing: PublicPricing


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


class ExtraIn(BaseModel):
    service_id: str = Field(min_length=1, max_length=32)
    quantity: int = Field(ge=1, le=1000)


class QuoteIn(BaseModel):
    items: list[QuoteItemIn] = Field(default_factory=list, max_length=20)
    services: ServicesIn = Field(default_factory=ServicesIn)
    extras: list[ExtraIn] = Field(default_factory=list, max_length=30)
    promo_code: str | None = Field(default=None, max_length=20)


class OrderCreateIn(QuoteIn):
    customer_name: str = Field(min_length=2, max_length=80)
    customer_phone: str = Field(default="", max_length=20)  # optional
    customer_email: EmailStr | None = None  # optional

    @field_validator("customer_email", mode="before")
    @classmethod
    def _empty_email(cls, v):
        return None if isinstance(v, str) and not v.strip() else v
    notify: bool = True
    note: str = Field(default="", max_length=500)


class QuoteLine(BaseModel):
    kind: Literal["print", "photocopy", "scan", "service", "discount", "minimum"]
    label: str
    document_id: str | None
    filename: str | None
    options: PrintOptions | None
    pages: int
    copies: int
    sheets: int
    unit_cents: int
    subtotal_cents: int
    document_pages: int | None = None  # page count of the original document (print lines)
    selected_pages: list[int] | None = None  # exactly what is printed, in the customer's order


class QuoteOut(BaseModel):
    lines: list[QuoteLine]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    total_ht_cents: int
    vat_cents: int
    vat_rate_bp: int
    promo_code_applied: str | None = None
    promo_error: str | None = None
    currency: Literal["EUR"] = "EUR"


class TrackIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)
    phone: str = Field(default="", max_length=20)  # required only if the order was placed with a phone


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
    total_ht_cents: int | None = None
    vat_cents: int | None = None
    vat_rate_bp: int | None = None
    discount_cents: int = 0
    currency: str
    created_at: datetime
    history: list[StatusEvent]
    documents_deleted: bool = False  # files erased (pickup / cancellation)


# ---------- orders (dashboard) ----------
class OrderOut(BaseModel):
    id: str
    code: str
    shop_id: str
    service: Literal["print", "copy", "scan"] = "print"
    delivery_token: str | None = None  # scan orders: secret customer download link
    scan_downloaded_at: datetime | None = None
    shop_name: str
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    notify: bool = True
    note: str
    lines: list[QuoteLine]
    total_cents: int
    total_ht_cents: int | None = None
    vat_cents: int | None = None
    vat_rate_bp: int | None = None
    discount_cents: int = 0
    currency: str
    status: OrderStatus
    payment_status: PaymentStatus
    payment_method: str | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
    history: list[StatusEvent]
    purged_at: datetime | None = None  # document files erased (pickup / cancellation); order data kept
    copy_job: "CopyJobOut | None" = None  # automatic photocopy (scan + print by the Windows agent)


class CopyJobOut(BaseModel):
    state: Literal["running", "needs_confirmation", "done", "failed"]
    printer_id: str
    printer_name: str
    source: Literal["flatbed", "feeder"] = "flatbed"
    copies_requested: int
    scanned_pages: int = 0
    copies_printed: int | None = None  # None = not reported reliably
    error: str = ""
    confirmed_by: str = ""
    phase: Literal["waiting", "scanning", "printing"] = "waiting"  # live progress reported by the agent
    progress_scanned: int = 0
    progress_printed_pages: int = 0  # pages the Windows spooler reports as printed so far
    total_print_pages: int = 0  # pages × copies to print (known once the scan is finished)


class AgentCopyProgressIn(BaseModel):
    phase: Literal["scanning", "printing"]
    scanned_pages: int = Field(default=0, ge=0, le=10_000)
    printed_pages: int = Field(default=0, ge=0, le=100_000)
    total_pages: int = Field(default=0, ge=0, le=100_000)


class CopyConfirmIn(BaseModel):
    originals: int = Field(ge=0, le=500)  # pages really in the original
    copies: int = Field(ge=0, le=500)  # complete copies that really came out


class OrderStatusIn(BaseModel):
    status: OrderStatus
    confirm_code: str = Field(default="", max_length=20)  # scanned/typed pickup code, required for picked_up


class DocumentHealthOut(BaseModel):
    document_id: str
    available: bool  # False = file referenced by the order but missing from storage (lost) — not a pickup deletion


class OrderDocumentsHealthOut(BaseModel):
    documents: list[DocumentHealthOut]
    resend_requested_at: datetime | None = None


class ResendRequestOut(BaseModel):
    sent_email: bool
    sent_sms: bool
    upload_url: str
    resend_requested_at: datetime


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
    plan: str
    subscription: SubscriptionOut | None = None
    owner_email: str
    shops_count: int
    orders_count: int
    revenue_cents: int
    created_at: datetime


class AdminOrgUpdateIn(BaseModel):
    status: Literal["active", "suspended"] | None = None


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
JobStatus = Literal["queued", "claimed", "spooled", "printing", "printed", "failed", "retry_wait", "cancelled"]


class PrintJobOut(BaseModel):
    id: str
    order_id: str
    order_code: str
    line_index: int
    filename: str | None
    kind: Literal["initial", "reprint"]
    reason: str
    status: JobStatus
    printer_id: str | None = None
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
    update_available: bool = False
    latest_version: str = ""
    scanners: list[str] = Field(default_factory=list)
    scanner_caps: list["ScannerCaps"] = Field(default_factory=list)


class PrinterCapabilities(BaseModel):
    paper_sizes: list[str] = Field(default_factory=list, max_length=60)  # as reported by the driver
    color: bool | None = None  # None = not reported by the driver
    duplex: bool | None = None
    orientations: list[str] = Field(default_factory=lambda: ["portrait", "landscape"])
    qualities: list[str] = Field(default_factory=list, max_length=10)


ConnectionType = Literal["usb", "wifi", "ethernet", "network", "virtual", "unknown"]


class PrinterOut(BaseModel):
    id: str
    agent_id: str
    name: str
    display_name: str = ""
    connection_type: ConnectionType = "unknown"
    connection_confirmed: bool = False
    manufacturer: str = ""
    model: str = ""
    ip_address: str = ""
    port_name: str = ""
    driver_name: str = ""
    driver_ok: bool | None = None
    capabilities: PrinterCapabilities = Field(default_factory=PrinterCapabilities)
    agent_name: str = ""
    active_jobs: int = 0
    is_default: bool
    enabled: bool
    status: Literal["online", "offline", "error"]
    status_detail: str
    supports_color: bool
    online: bool
    last_seen_at: datetime | None
    verified_at: datetime | None = None  # last successful test by the agent (« Prête » requires it)


class PrinterUpdateIn(BaseModel):
    enabled: bool | None = None
    is_default: bool | None = None
    display_name: str | None = Field(default=None, max_length=80)
    connection_type: Literal["usb", "wifi", "ethernet", "network"] | None = None  # owner confirms the real link


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
    connection_type: ConnectionType = "unknown"
    manufacturer: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=150)
    ip_address: str = Field(default="", max_length=100)
    port_name: str = Field(default="", max_length=200)
    driver_name: str = Field(default="", max_length=200)
    driver_ok: bool | None = None
    capabilities: PrinterCapabilities = Field(default_factory=PrinterCapabilities)
    is_default: bool = False
    status: Literal["online", "offline", "error"] = "online"
    detail: str = Field(default="", max_length=200)
    supports_color: bool = True


class AgentHeartbeatIn(BaseModel):
    version: str = Field(default="", max_length=20)
    drivers: list[str] = Field(default_factory=list, max_length=300)
    printers: list[AgentPrinterIn] = Field(default_factory=list, max_length=50)
    scanners: list[str] = Field(default_factory=list, max_length=20)  # WIA scanners seen by the agent
    scanner_caps: list["ScannerCaps"] = Field(default_factory=list, max_length=20)


class ScannerCaps(BaseModel):
    name: str = Field(max_length=200)
    flatbed: bool = True
    feeder: bool = False
    duplex: bool = False


class AgentCommandOut(BaseModel):
    id: str
    type: Literal["discover_usb", "discover_network", "discover_all", "install_printer", "add_network_printer", "test_connection", "test_page", "scan", "copy", "self_update"]
    payload: dict[str, Any]


class AgentHeartbeatOut(BaseModel):
    shop_name: str
    poll_seconds: int
    commands: list[AgentCommandOut] = Field(default_factory=list)


class AgentCommandResultIn(BaseModel):
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = Field(default="", max_length=500)


class CommandOut(BaseModel):
    id: str
    type: str
    status: Literal["queued", "sent", "done", "failed", "expired"]
    result: dict[str, Any]
    error: str
    created_at: datetime


class AgentRefIn(BaseModel):
    agent_id: str


class ConnectPrinterIn(BaseModel):
    agent_id: str
    name: str = Field(min_length=1, max_length=200)  # Windows queue name


class InstallPrinterIn(BaseModel):
    agent_id: str
    kind: Literal["network", "usb"]
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(default="", max_length=100)
    ipp_path: str = Field(default="ipp/print", max_length=120)
    device_id: str = Field(default="", max_length=300)  # USB: Windows PnP instance id
    manufacturer: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=150)
    connection_type: Literal["wifi", "ethernet", "network", "usb"] = "network"


class DiscoverIn(BaseModel):
    agent_id: str
    kind: Literal["usb", "network"]


class ManualPrinterIn(BaseModel):
    agent_id: str
    name: str = Field(min_length=2, max_length=80)
    host: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9.\-:]+$")
    protocol: Literal["ipp", "raw9100", "lpd"]
    port: int | None = Field(default=None, ge=1, le=65535)
    queue: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9_./\-]*$")
    driver_name: str = Field(default="", max_length=200)
    connection_type: Literal["wifi", "ethernet", "network"] = "network"


class PrinterRule(BaseModel):
    id: str = Field(default="", max_length=32)
    service: Literal["print", "any"] = "print"
    paper_size: str = Field(default="any", max_length=10)
    color: Literal["bw", "color", "any"] = "any"
    printer_id: str


class PrinterRulesIO(BaseModel):
    rules: list[PrinterRule] = Field(default_factory=list, max_length=30)


class PrintDirectIn(BaseModel):
    printer_id: str | None = None  # None = automatic assignment (rules, then default)
    dry_check: bool = False


class PrintCheckLine(BaseModel):
    line_index: int
    filename: str | None
    printer_id: str | None
    printer_name: str | None
    problems: list[str]
    warnings: list[str]


class PrintCheckOut(BaseModel):
    ok: bool
    problems: list[str]
    lines: list[PrintCheckLine]
    jobs_created: int = 0


class ReassignIn(BaseModel):
    printer_id: str


class OnboardingStep(BaseModel):
    key: str
    label: str
    done: bool
    auto: bool
    link: str


class TrackingConfigOut(BaseModel):
    ads_purchase_send_to: str = ""  # Google Ads « AW-…/label » for the purchase conversion


class AgentUpdateItem(BaseModel):
    agent_id: str
    name: str
    shop_name: str
    reason: str = ""  # why it was skipped ("" when started)


class UpdateAllOut(BaseModel):
    version: str
    started: list[AgentUpdateItem]
    skipped: list[AgentUpdateItem]


class AgentDownloadOut(BaseModel):
    available: bool
    url: str
    version: str
    notes: str = ""
    sha256: str = ""
    size_bytes: int = 0


class AgentReleaseIn(BaseModel):
    url: str = Field(default="", max_length=500)  # "" = download disabled
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    notes: str = Field(default="", max_length=500)


class AgentReleaseOut(BaseModel):
    url: str  # what shops download (printdrop.fr file if uploaded, else external link)
    version: str
    notes: str
    updated_at: datetime | None
    external_url: str = ""
    filename: str = ""  # installer uploaded to printdrop.fr ("" = none)
    sha256: str = ""
    size_bytes: int = 0


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
    status: Literal["spooled", "printing", "printed", "failed", "requeue"]
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


# ---------- SaaS billing ----------
BillingPeriod = Literal["monthly", "yearly"]


class PlanPrices(BaseModel):
    monthly: int | None = Field(default=None, ge=0, le=100_000_00)  # HT cents, None = not offered
    yearly: int | None = Field(default=None, ge=0, le=1_000_000_00)


class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    description: str = Field(default="", max_length=200)
    prices_ht: PlanPrices
    features: list[str] = Field(default_factory=list, max_length=20)
    max_shops: int = Field(ge=1, le=1000)
    max_staff: int = Field(ge=1, le=10_000)
    active: bool = True
    sort: int = Field(default=0, ge=0, le=100)

    @field_validator("features")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        return [f.strip()[:120] for f in v if f.strip()]


class PlanOut(PlanIn):
    code: str
    vat_rate_bp: int
    prices_ttc: PlanPrices


class PlatformSettingsIn(BaseModel):
    shop_vat_rate_bp: int = Field(ge=0, le=5000)
    subscription_vat_rate_bp: int = Field(ge=0, le=5000)
    trial_days: int = Field(ge=0, le=90)
    grace_days: int = Field(ge=0, le=60)
    company_name: str = Field(min_length=2, max_length=80)
    company_address: str = Field(default="", max_length=200)
    company_siret: str = Field(default="", max_length=20)
    company_vat_number: str = Field(default="", max_length=20)
    company_email: str = Field(default="", max_length=120)


class PlatformSettingsOut(PlatformSettingsIn):
    payment_provider: str
    payment_configured: bool
    payment_mode: Literal["test", "live", "none"]


class CheckoutIn(BaseModel):
    plan_code: str = Field(min_length=2, max_length=20)
    period: BillingPeriod


class CheckoutOut(BaseModel):
    invoice_id: str
    checkout_url: str


class InvoiceOut(BaseModel):
    id: str
    number: str | None
    status: Literal["pending", "paid", "failed", "canceled", "expired"]
    plan_code: str
    plan_name: str
    period: BillingPeriod
    amount_ht_cents: int
    vat_rate_bp: int
    vat_cents: int
    amount_ttc_cents: int
    provider: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    created_at: datetime
    paid_at: datetime | None = None
    buyer_name: str
    seller: dict[str, str]


class BillingOverviewOut(BaseModel):
    subscription: SubscriptionOut
    payment_configured: bool
    payment_mode: Literal["test", "live", "none"]
    plans: list[PlanOut]
    invoices: list[InvoiceOut]
    usage_shops: int
    usage_staff: int


class AdminSubscriptionIn(BaseModel):
    plan_code: str | None = Field(default=None, max_length=20)
    period: BillingPeriod | None = None
    status: Literal["trialing", "active", "canceled"] | None = None
    period_end: datetime | None = None


# ---------- marketing site ----------
class PublicPlanOut(BaseModel):
    code: str
    name: str
    description: str
    features: list[str]
    monthly_ht_cents: int
    yearly_ht_cents: int | None = None


class ContactIn(BaseModel):
    kind: Literal["contact", "demo"] = "contact"
    name: str = Field(min_length=2, max_length=100)
    business: str = Field(default="", max_length=120)
    email: EmailStr
    subject: str = Field(min_length=2, max_length=150)
    message: str = Field(min_length=10, max_length=4000)
    website: str = Field(default="", max_length=200)  # honeypot, must stay empty


class ContactOut(BaseModel):
    ok: bool
    delivered: bool  # False = stored but not e-mailed (email not configured or failed)


class ContactMessageOut(BaseModel):
    id: str
    kind: Literal["contact", "demo"]
    name: str
    business: str
    email: str
    subject: str
    message: str
    created_at: datetime
    delivered: bool
    handled: bool = False
    handled_at: datetime | None = None


class ContactMessageUpdateIn(BaseModel):
    handled: bool


# ---------- counter services (photocopy / scan) ----------
class CopyIn(BaseModel):
    color: Literal["bw", "color"] = "bw"
    paper_size: Literal["A4", "A3"] = "A4"
    duplex: bool = False
    originals: int = Field(default=1, ge=1, le=500)  # manual copy only: pages of the paper original
    copies: int = Field(default=1, ge=1, le=500)
    customer_name: str = Field(default="", max_length=80)
    printer_id: str | None = None  # set = automatic copy (agent scans then prints); None = copier's own Copy button
    source: Literal["flatbed", "feeder"] = "flatbed"


class ScanSessionIn(BaseModel):
    agent_id: str | None = None  # None = import files from the scanner software only
    format: Literal["pdf", "jpg"] = "pdf"
    color: Literal["bw", "color"] = "color"
    dpi: Literal[150, 200, 300, 600] = 300
    source: Literal["flatbed", "feeder"] = "flatbed"
    duplex: bool = False


class ScanPageOut(BaseModel):
    id: str
    index: int
    rotation: int
    width: int
    height: int


class ScanSessionOut(BaseModel):
    id: str
    shop_id: str
    agent_id: str | None
    format: Literal["pdf", "jpg"]
    color: Literal["bw", "color"]
    dpi: int
    source: Literal["flatbed", "feeder"]
    status: Literal["open", "scanning", "finalized"]
    error: str
    order_id: str | None
    pages: list[ScanPageOut]
    agent_online: bool
    scanners: list[str]
    scanner_caps: list[ScannerCaps] = Field(default_factory=list)
    duplex: bool = False
    created_at: datetime


class ScanPageUpdateIn(BaseModel):
    rotation: Literal[0, 90, 180, 270]


class ScanFinalizeIn(BaseModel):
    customer_name: str = Field(default="", max_length=80)
    customer_email: EmailStr | None = None

    @field_validator("customer_email", mode="before")
    @classmethod
    def _empty(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class ScanEmailIn(BaseModel):
    email: EmailStr


class ScanPublicOut(BaseModel):
    shop_name: str
    filename: str
    pages: int
    kind: str
    paid: bool
    available: bool
    first_download_at: datetime | None


# ---------- cash-up (clôture de caisse) ----------
class CashPaymentOut(BaseModel):
    at: datetime
    order_code: str
    service: str
    method: str
    amount_cents: int


class CashSummaryOut(BaseModel):
    day: str
    shop_id: str
    shop_name: str
    shop_address: str
    cash_cents: int
    cash_count: int
    card_cents: int
    card_count: int
    other_cents: int  # online or any other method
    other_count: int
    total_cents: int
    total_count: int
    payments: list[CashPaymentOut]
    generated_at: datetime


OrderOut.model_rebuild()
AgentOut.model_rebuild()
AgentHeartbeatIn.model_rebuild()
