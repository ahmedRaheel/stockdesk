/** Shared HTTP boundary. The browser uses HttpOnly sessions, never bearer storage. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public requestId: string | null,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const fields = payload?.fields
      ?.map((f: { path: string; message: string }) => `${f.path}: ${f.message}`)
      .join("; ");
    throw new ApiError(
      fields || payload?.error || `Request failed (${response.status}).`,
      response.status,
      response.headers.get("X-Request-ID"),
    );
  }
  return payload as T;
}
export function send<T>(
  path: string,
  payload: unknown,
  method = "POST",
): Promise<T> {
  return api<T>(path, { method, body: JSON.stringify(payload) });
}
