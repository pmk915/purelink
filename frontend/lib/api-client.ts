import type { ApiErrorPayload } from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export class ApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

type RequestOptions = {
  method?: string;
  token?: string | null;
  body?: BodyInit | null;
  json?: unknown;
  headers?: HeadersInit;
};

function getBrowserOrigin() {
  if (typeof window === "undefined") {
    return null;
  }

  return window.location.origin;
}

function logRequestFailure(details: Record<string, unknown>) {
  if (typeof window === "undefined") {
    return;
  }

  console.error("PureLink API request failed", details);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);

  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  let body = options.body ?? null;

  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  }

  const requestUrl = `${API_BASE_URL}${path}`;
  const requestMethod = options.method ?? "GET";
  const currentOrigin = getBrowserOrigin();
  let response: Response;

  try {
    response = await fetch(requestUrl, {
      method: requestMethod,
      headers,
      body,
      cache: "no-store"
    });
  } catch (error) {
    logRequestFailure({
      error,
      requestUrl,
      requestMethod,
      apiBaseUrl: API_BASE_URL,
      currentOrigin,
      hasAuthorization: headers.has("Authorization"),
      contentType: headers.get("Content-Type"),
      bodyType:
        body instanceof FormData ? "FormData" : body instanceof URLSearchParams ? "URLSearchParams" : typeof body
    });

    const apiOrigin = (() => {
      try {
        return new URL(API_BASE_URL).origin;
      } catch {
        return API_BASE_URL;
      }
    })();

    const isCrossOrigin = currentOrigin !== null && apiOrigin !== currentOrigin;
    const detail = isCrossOrigin
      ? "Unable to connect to the server. Check that the backend is running and that the browser is allowed to access it across origins."
      : "Unable to connect to the server. Check that the backend is running and reachable.";

    throw new ApiClientError(detail, 0);
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;

    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Ignore JSON parsing errors for non-JSON responses.
    }

    throw new ApiClientError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

async function requestBlob(path: string, token?: string | null): Promise<Blob> {
  const headers = new Headers();

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
    headers,
    cache: "no-store"
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;

    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Binary endpoints may return non-JSON error bodies.
    }

    throw new ApiClientError(detail, response.status);
  }

  return response.blob();
}

export const apiClient = {
  get: <T>(path: string, token?: string | null) =>
    request<T>(path, { method: "GET", token }),
  post: <T>(path: string, json?: unknown, token?: string | null) =>
    request<T>(path, { method: "POST", json, token }),
  patch: <T>(path: string, json?: unknown, token?: string | null) =>
    request<T>(path, { method: "PATCH", json, token }),
  delete: <T>(path: string, token?: string | null) =>
    request<T>(path, { method: "DELETE", token }),
  getBlob: (path: string, token?: string | null) => requestBlob(path, token),
  upload: <T>(path: string, file: File, token?: string | null) => {
    const formData = new FormData();
    formData.append("file", file);

    if (typeof window !== "undefined") {
      console.info("PureLink upload request", {
        apiBaseUrl: API_BASE_URL,
        requestUrl: `${API_BASE_URL}${path}`,
        requestMethod: "POST",
        currentOrigin: window.location.origin,
        fieldName: "file",
        file: {
          name: file.name,
          type: file.type,
          size: file.size
        }
      });
    }

    return request<T>(path, { method: "POST", body: formData, token });
  }
};
