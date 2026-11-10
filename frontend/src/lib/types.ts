// Hand-written mirrors of backend/models/schemas.py — keep in sync when a Pydantic model changes.

export type PaperSize = "A4" | "A3" | "A5" | "Letter" | "Legal";
export type ColorMode = "bw" | "color";
export type OrderStatus = "pending" | "printing" | "ready" | "picked_up" | "delivered" | "cancelled";
export type PaymentStatus = "unpaid" | "paid_counter" | "paid_online";
export type TenantRole = "owner" | "manager" | "operator";

export interface ColorPrice { bw: number; color: number; active: boolean }
export type ServiceCategory = "typing" | "binding" | "lamination" | "custom";
export interface ServiceItem {
  id: string; name: string; category: ServiceCategory; unit: "page" | "unit" | "document"; price_cents: number;
  price_from: boolean; description: string; active: boolean;
}
export interface PricingRule { id: string; name: string; min_pages: number; discount_pct: number; active: boolean }
export interface Discount {
  id: string; name: string; code: string | null; kind: "percent" | "fixed"; value: number; min_order_cents: number; active: boolean;
}
export interface Pricing {
  print: Record<PaperSize, ColorPrice>;
  duplex_discount_pct: number;
  photocopy: ColorPrice;
  scan_cents: number;
  scan_color_cents?: number | null;
  min_order_cents: number;
  services: ServiceItem[];
  rules: PricingRule[];
  discounts: Discount[];
}
export interface AutoDiscountOut { name: string; kind: "percent" | "fixed"; value: number; min_order_cents: number }
export interface PublicPricing {
  print: Record<PaperSize, ColorPrice>; duplex_discount_pct: number; photocopy: ColorPrice; scan_cents: number; scan_color_cents?: number | null;
  min_order_cents: number; services: ServiceItem[]; rules: PricingRule[]; auto_discounts: AutoDiscountOut[];
  has_promo_codes: boolean; vat_rate_bp: number;
}
export type SubscriptionStatus = "trialing" | "active" | "past_due" | "expired" | "canceled";
export interface SubscriptionOut {
  plan_code: string; plan_name: string; period: "monthly" | "yearly"; status: SubscriptionStatus;
  trial_ends_at: string | null; current_period_end: string | null; granted_by_admin: boolean; days_left: number | null;
}

export interface UserOut { id: string; email: string; name: string }
export interface OrgOut { id: string; name: string; status: string; plan: string; subscription: SubscriptionOut | null }
export interface ShopOut {
  id: string; org_id: string; slug: string; name: string; city: string; address: string;
  accepting_orders: boolean; pricing: Pricing; created_at: string;
}
export interface MeOut {
  user: UserOut; platform_role: string | null; org: OrgOut | null; role: TenantRole | null;
  permissions: string[]; shops: ShopOut[];
}
export interface RegisterIn { org_name: string; shop_name: string; city: string; owner_name: string; email: string; password: string }
export interface LoginIn { email: string; password: string }
export interface ShopCreateIn { name: string; city: string; address: string }
export interface ShopUpdateIn { name?: string; city?: string; address?: string; accepting_orders?: boolean }

export interface PublicShopOut { slug: string; name: string; city: string; address: string; accepting_orders: boolean; pricing: PublicPricing }
export interface DocumentUploadOut { id: string; filename: string; kind: string; page_count: number; size_bytes: number; upload_token: string }
export interface PrintOptions { paper_size: PaperSize; color: ColorMode; duplex: boolean; copies: number; page_range: string }
export interface QuoteItemIn { document_id: string; upload_token: string; options: PrintOptions }
export interface ServicesIn { photocopy_bw: number; photocopy_color: number; scan_pages: number }
export interface ExtraIn { service_id: string; quantity: number }
export interface QuoteIn { items: QuoteItemIn[]; services: ServicesIn; extras: ExtraIn[]; promo_code: string | null }
export interface OrderCreateIn extends QuoteIn { customer_name: string; customer_phone: string; customer_email: string | null; notify: boolean; note: string }
export interface QuoteLine {
  kind: "print" | "photocopy" | "scan" | "service" | "discount" | "minimum"; label: string; document_id: string | null; filename: string | null;
  options: PrintOptions | null; pages: number; copies: number; sheets: number; unit_cents: number; subtotal_cents: number;
  document_pages?: number | null; selected_pages?: number[] | null;
}
export interface QuoteOut {
  lines: QuoteLine[]; subtotal_cents: number; discount_cents: number; total_cents: number; total_ht_cents: number;
  vat_cents: number; vat_rate_bp: number; promo_code_applied: string | null; promo_error: string | null; currency: "EUR";
}
export interface TrackIn { code: string; phone: string }
export interface StatusEvent { status: OrderStatus; at: string; by: string }
export interface OrderPublicOut {
  code: string; shop_name: string; shop_slug: string; status: OrderStatus; payment_status: PaymentStatus;
  lines: QuoteLine[]; total_cents: number; total_ht_cents: number | null; vat_cents: number | null; vat_rate_bp: number | null;
  discount_cents: number; currency: string; created_at: string; history: StatusEvent[];
  documents_deleted: boolean;
}

export interface DocumentHealthOut {
  document_id: string;
  available: boolean;
}

export interface OrderDocumentsHealthOut {
  documents: DocumentHealthOut[];
  resend_requested_at: string | null;
}

export interface ResendRequestOut {
  sent_email: boolean;
  sent_sms: boolean;
  upload_url: string;
  resend_requested_at: string;
}

export interface OrderOut {
  id: string; code: string; shop_id: string; service?: "print" | "copy" | "scan"; delivery_token?: string | null; scan_downloaded_at?: string | null; shop_name: string; customer_name: string; customer_phone: string;
  customer_email: string | null; notify: boolean; note: string; lines: QuoteLine[]; total_cents: number;
  total_ht_cents: number | null; vat_cents: number | null; vat_rate_bp: number | null; discount_cents: number; currency: string; status: OrderStatus;
  payment_status: PaymentStatus; payment_method: string | null; paid_at: string | null;
  created_at: string; updated_at: string; history: StatusEvent[]; purged_at?: string | null; copy_job?: CopyJobOut | null;
}
export interface OrderStatusIn { status: OrderStatus ; confirm_code?: string }
export interface OrderPayIn { method: "cash" | "card_terminal" }
export interface DownloadLinkOut { url: string; expires_at: number }
export interface ShopStatsOut {
  orders_today: number; pending: number; printing: number; ready: number; revenue_today_cents: number; unpaid_cents: number;
}

export interface StaffOut { membership_id: string; user_id: string; name: string; email: string; role: TenantRole; active: boolean; created_at: string }
export interface StaffCreateIn { name: string; email: string; password: string; role: "manager" | "operator" }
export interface StaffUpdateIn { role?: "manager" | "operator"; active?: boolean }

export interface AuditOut {
  id: string; at: string; actor_email: string; action: string; resource_type: string; resource_id: string;
  outcome: string; details: Record<string, unknown>;
}

export interface AdminStatsOut { organizations: number; active_organizations: number; shops: number; users: number; orders: number; revenue_cents: number }
export interface AdminOrgOut {
  id: string; name: string; status: "active" | "suspended"; plan: string; subscription: SubscriptionOut | null; owner_email: string;
  shops_count: number; orders_count: number; revenue_cents: number; created_at: string;
}
export interface AdminOrgUpdateIn { status?: "active" | "suspended" }

export interface NotificationOut {
  id: string; channel: "email" | "sms"; recipient: string; status: "queued" | "sending" | "sent" | "failed" | "skipped";
  attempts: number; last_error: string | null; created_at: string; sent_at: string | null;
}
export interface NotificationStatusOut { email_configured: boolean; sms_configured: boolean }

export type JobStatus = "queued" | "claimed" | "spooled" | "printing" | "printed" | "failed" | "retry_wait" | "cancelled";
export interface PrintJobOut {
  id: string; order_id: string; order_code: string; line_index: number; filename: string | null; kind: "initial" | "reprint";
  reason: string; status: JobStatus; printer_id: string | null; printer_name: string | null; error: string | null; requested_by: string;
  created_at: string; updated_at: string; printed_at: string | null;
}
export interface ReprintIn { reason: string }
export interface PairingCodeOut { code: string; expires_at: string }
export interface AgentOut {
  id: string; name: string; hostname: string; version: string; status: "active" | "revoked"; online: boolean;
  last_seen_at: string | null; created_at: string; update_available: boolean; latest_version: string;
  scanners?: string[]; scanner_caps?: ScannerCaps[];
}
export interface PrinterOut {
  id: string; agent_id: string; name: string; is_default: boolean; enabled: boolean; status: "online" | "offline" | "error";
  status_detail: string; supports_color: boolean; online: boolean; last_seen_at: string | null;
  display_name: string; connection_type: "usb" | "wifi" | "ethernet" | "network" | "virtual" | "unknown"; connection_confirmed: boolean;
  manufacturer: string; model: string; ip_address: string; port_name: string; driver_name: string; driver_ok: boolean | null;
  capabilities: PrinterCapabilities; agent_name: string; active_jobs: number; verified_at?: string | null;
}
export interface PrinterUpdateIn { enabled?: boolean; is_default?: boolean; display_name?: string; connection_type?: "usb" | "wifi" | "ethernet" | "network" }
export interface PrinterCapabilities { paper_sizes: string[]; color: boolean | null; duplex: boolean | null; orientations: string[]; qualities: string[] }
export interface CommandOut { id: string; type: string; status: "queued" | "sent" | "done" | "failed" | "expired"; result: Record<string, unknown>; error: string; created_at: string }
export interface ManualPrinterIn { agent_id: string; name: string; host: string; protocol: "ipp" | "raw9100" | "lpd"; port: number | null; queue: string; driver_name: string; connection_type: "wifi" | "ethernet" | "network" }
export interface PrinterRule { id: string; service: "print" | "any"; paper_size: string; color: "bw" | "color" | "any"; printer_id: string }
export interface PrinterRulesIO { rules: PrinterRule[] }
export interface PrintDirectIn { printer_id: string | null; dry_check: boolean }
export interface PrintCheckLine { line_index: number; filename: string | null; printer_id: string | null; printer_name: string | null; problems: string[]; warnings: string[] }
export interface PrintCheckOut { ok: boolean; problems: string[]; lines: PrintCheckLine[]; jobs_created: number }
export interface OnboardingStep { key: string; label: string; done: boolean; auto: boolean; link: string }
export interface AgentDownloadOut { available: boolean; url: string; version: string; notes: string }
export interface AgentReleaseIn { url: string; version: string; notes: string }
export interface AgentReleaseOut extends AgentReleaseIn { updated_at: string | null }

export interface AlertOut {
  kind: "agent_offline" | "printer_offline" | "job_failed" | "low_paper"; message: string; since: string;
  printer_name: string | null; order_id: string | null; order_code: string | null;
}
export interface HourBucket { hour: number; orders: number; revenue_cents: number }
export interface DailyReportOut {
  day: string; shop_id: string; shop_name: string; orders_total: number; orders_cancelled: number; orders_picked_up: number;
  revenue_cents: number; revenue_cash_cents: number; revenue_card_cents: number; payments_count: number; avg_basket_cents: number;
  unpaid_cents: number; pages_bw: number; pages_color: number; sheets: number; photocopies: number; scans: number;
  jobs_printed: number; jobs_failed: number; busiest_hour: number | null; hours: HourBucket[];
}
export interface ReportSettingsIn { daily_email: boolean }
export interface ReportSettingsOut { daily_email: boolean; recipient: string }

export interface PaperLevelOut {
  paper_size: PaperSize; stock_sheets: number; used_sheets: number; remaining_sheets: number; pct_used: number;
  set_at: string; level: "ok" | "low" | "out";
}
export interface PaperStockOut { alert_pct: number; levels: PaperLevelOut[] }
export interface PaperStockIn { stock: Partial<Record<PaperSize, number | null>>; alert_pct: number }

export type BillingPeriod = "monthly" | "yearly";
export interface PlanPrices { monthly: number | null; yearly: number | null }
export interface PlanIn {
  name: string; description: string; prices_ht: PlanPrices; features: string[]; max_shops: number; max_staff: number; active: boolean; sort: number;
}
export interface PlanOut extends PlanIn { code: string; vat_rate_bp: number; prices_ttc: PlanPrices }
export interface PlatformSettingsIn {
  shop_vat_rate_bp: number; subscription_vat_rate_bp: number; trial_days: number; grace_days: number;
  company_name: string; company_address: string; company_siret: string; company_vat_number: string; company_email: string;
}
export interface PlatformSettingsOut extends PlatformSettingsIn { payment_provider: string; payment_configured: boolean; payment_mode: "test" | "live" | "none" }
export interface CheckoutIn { plan_code: string; period: BillingPeriod }
export interface CheckoutOut { invoice_id: string; checkout_url: string }
export interface InvoiceOut {
  id: string; number: string | null; status: "pending" | "paid" | "failed" | "canceled" | "expired"; plan_code: string; plan_name: string;
  period: BillingPeriod; amount_ht_cents: number; vat_rate_bp: number; vat_cents: number; amount_ttc_cents: number; provider: string;
  period_start: string | null; period_end: string | null; created_at: string; paid_at: string | null; buyer_name: string; seller: Record<string, string>;
}
export interface BillingOverviewOut {
  subscription: SubscriptionOut; payment_configured: boolean; payment_mode: "test" | "live" | "none"; plans: PlanOut[];
  invoices: InvoiceOut[]; usage_shops: number; usage_staff: number;
}
export interface AdminSubscriptionIn { plan_code?: string; period?: BillingPeriod; status?: "trialing" | "active" | "canceled"; period_end?: string }

// ---------- marketing site ----------
export interface PublicPlanOut { code: string; name: string; description: string; features: string[]; monthly_ht_cents: number; yearly_ht_cents: number | null }
export interface ContactIn { kind: "contact" | "demo"; name: string; business: string; email: string; subject: string; message: string; website: string }
export interface ContactOut { ok: boolean; delivered: boolean }
export interface ContactMessageOut {
  id: string; kind: "contact" | "demo"; name: string; business: string; email: string; subject: string; message: string;
  created_at: string; delivered: boolean; handled: boolean; handled_at: string | null;
}
export interface ContactMessageUpdateIn { handled: boolean }

// ---------- counter services ----------
export interface CopyIn { color: "bw" | "color"; paper_size: "A4" | "A3"; duplex: boolean; originals: number; copies: number; customer_name: string; printer_id: string | null; source: "flatbed" | "feeder" }
export interface CopyJobOut {
  state: "running" | "needs_confirmation" | "done" | "failed"; printer_id: string; printer_name: string; source: "flatbed" | "feeder";
  copies_requested: number; scanned_pages: number; copies_printed: number | null; error: string; confirmed_by: string;
}
export interface CopyConfirmIn { originals: number; copies: number }
export interface ScannerCaps { name: string; flatbed: boolean; feeder: boolean; duplex: boolean }
export interface InstallPrinterIn {
  agent_id: string; kind: "network" | "usb"; name: string; host: string; ipp_path: string; device_id: string;
  manufacturer: string; model: string; connection_type: "wifi" | "ethernet" | "network" | "usb";
}
export interface DiscoveredNetwork { ip_address: string; hostname: string; protocols: string[]; already_installed: boolean; manufacturer: string; model: string }
export interface DiscoveredUsb { name: string; device_id: string; manufacturer: string; error_code: number | null }
export interface ScanSessionIn { agent_id: string | null; format: "pdf" | "jpg"; color: "bw" | "color"; dpi: 150 | 200 | 300 | 600; source: "flatbed" | "feeder"; duplex: boolean }
export interface ScanPageOut { id: string; index: number; rotation: number; width: number; height: number }
export interface ScanSessionOut extends ScanSessionIn {
  id: string; shop_id: string; status: "open" | "scanning" | "finalized"; error: string; order_id: string | null;
  pages: ScanPageOut[]; agent_online: boolean; scanners: string[]; scanner_caps: ScannerCaps[]; created_at: string;
}
export interface ScanFinalizeIn { customer_name: string; customer_email: string | null }
export interface ScanPublicOut { shop_name: string; filename: string; pages: number; kind: string; paid: boolean; available: boolean; first_download_at: string | null }

// ---------- cash-up ----------
export interface CashPaymentOut { at: string; order_code: string; service: string; method: string; amount_cents: number }
export interface CashSummaryOut {
  day: string; shop_id: string; shop_name: string; shop_address: string;
  cash_cents: number; cash_count: number; card_cents: number; card_count: number; other_cents: number; other_count: number;
  total_cents: number; total_count: number; payments: CashPaymentOut[]; generated_at: string;
}
