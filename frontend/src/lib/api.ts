// Typed fetch layer over the FastAPI backend. Base is the relative "/api" prefix so the
// same code works in dev (Vite proxies /api → :8001) and behind a single origin in prod.
const BASE = "/api";

// Fields are declared, not constructor parameter properties: tsconfig sets
// erasableSyntaxOnly, which rejects `constructor(readonly status: number)`.
export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`request failed with ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

type JsonBody = unknown;

async function request<T>(method: string, path: string, body?: JsonBody): Promise<T> {
  // Auth rides the httpOnly session cookie automatically — never add auth headers here.
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // FastAPI reports request-validation failures as 422 with a {detail: [...]} body.
  if (!res.ok) {
    const errBody = await res.json().catch(() => null);
    throw new ApiError(res.status, errBody);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// The response type is yours to declare: nothing infers across the Python boundary, so a
// TS interface here mirrors the endpoint's Pydantic model by hand — keep the two in sync.
export const apiGet = <T>(path: string) => request<T>("GET", path);
export const apiPost = <T>(path: string, body?: JsonBody) => request<T>("POST", path, body ?? null);
export const apiPut = <T>(path: string, body?: JsonBody) => request<T>("PUT", path, body ?? null);
export const apiPatch = <T>(path: string, body?: JsonBody) =>
  request<T>("PATCH", path, body ?? null);
export const apiDelete = <T>(path: string) => request<T>("DELETE", path);

// Multipart upload (browser sets the boundary header itself).
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file, file.name);
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    const errBody = await res.json().catch(() => null);
    throw new ApiError(res.status, errBody);
  }
  return (await res.json()) as T;
}

// French, user-facing message from any thrown error (FastAPI detail string or 422 list).
export function errorMessage(err: unknown, fallback = "Une erreur est survenue"): string {
  if (err instanceof ApiError) {
    const detail = (err.body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
      return `Champ invalide${field ? ` (${field})` : ""} : ${first.msg ?? ""}`;
    }
    if (err.status === 0 || err.status >= 500) return "Service indisponible, réessayez";
  }
  return fallback;
}
