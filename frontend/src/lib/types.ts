// Hand-written mirrors of backend/models/schemas.py — keep in sync when a Pydantic model changes.

export type PaperSize = "A4" | "A3" | "A5" | "Letter" | "Legal";
export type ColorMode = "bw" | "color";
export type OrderStatus = "pending" | "printing" | "ready" | "picked_up" | "cancelled";
export type PaymentStatus = "unpaid" | "paid_counter" | "paid_online";
export type TenantRole = "owner" | "manager" | "operator";

export interface ColorPrice { bw: number; color: number }
export interface Pricing {
  print: Record<PaperSize, ColorPrice>;
  duplex_discount_pct: number;
  photocopy: ColorPrice;
  scan_cents: number;
}

export interface UserOut { id: string; email: string; name: string }
export interface OrgOut { id: string; name: string; status: string; plan: string }
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

export interface PublicShopOut { slug: string; name: string; city: string; address: string; accepting_orders: boolean; pricing: Pricing }
export interface DocumentUploadOut { id: string; filename: string; kind: string; page_count: number; size_bytes: number; upload_token: string }
export interface PrintOptions { paper_size: PaperSize; color: ColorMode; duplex: boolean; copies: number; page_range: string }
export interface QuoteItemIn { document_id: string; upload_token: string; options: PrintOptions }
export interface ServicesIn { photocopy_bw: number; photocopy_color: number; scan_pages: number }
export interface QuoteIn { items: QuoteItemIn[]; services: ServicesIn }
export interface OrderCreateIn extends QuoteIn { customer_name: string; customer_phone: string; note: string }
export interface QuoteLine {
  kind: "print" | "photocopy" | "scan"; label: string; document_id: string | null; filename: string | null;
  options: PrintOptions | null; pages: number; copies: number; sheets: number; unit_cents: number; subtotal_cents: number;
}
export interface QuoteOut { lines: QuoteLine[]; total_cents: number; currency: "EUR" }
export interface TrackIn { code: string; phone: string }
export interface StatusEvent { status: OrderStatus; at: string; by: string }
export interface OrderPublicOut {
  code: string; shop_name: string; shop_slug: string; status: OrderStatus; payment_status: PaymentStatus;
  lines: QuoteLine[]; total_cents: number; currency: string; created_at: string; history: StatusEvent[];
}

export interface OrderOut {
  id: string; code: string; shop_id: string; shop_name: string; customer_name: string; customer_phone: string;
  note: string; lines: QuoteLine[]; total_cents: number; currency: string; status: OrderStatus;
  payment_status: PaymentStatus; payment_method: string | null; paid_at: string | null;
  created_at: string; updated_at: string; history: StatusEvent[];
}
export interface OrderStatusIn { status: OrderStatus }
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
  id: string; name: string; status: "active" | "suspended"; plan: "essai" | "starter" | "pro"; owner_email: string;
  shops_count: number; orders_count: number; revenue_cents: number; created_at: string;
}
export interface AdminOrgUpdateIn { status?: "active" | "suspended"; plan?: "essai" | "starter" | "pro" }
