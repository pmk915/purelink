export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
  request_id?: string | null;
}

export interface ApiErrorPayload {
  error?: ApiErrorDetail;
  detail?:
    | string
    | {
        code?: string;
        error_code?: string;
        message?: string;
        detail?: string;
        [key: string]: unknown;
      };
}

export class ApiError extends Error {
  status: number;
  code: string;
  errorCode: string | null;
  details: Record<string, unknown> | null;
  requestId: string | null;

  constructor({
    message,
    status,
    code,
    details = null,
    requestId = null
  }: {
    message: string;
    status: number;
    code: string;
    details?: Record<string, unknown> | null;
    requestId?: string | null;
  }) {
    super(message || "Request failed.");
    this.name = "ApiError";
    this.status = status;
    this.code = code || fallbackCodeForStatus(status);
    this.errorCode = this.code;
    this.details = details;
    this.requestId = requestId;
  }
}

export function fallbackCodeForStatus(status: number) {
  if (status === 0) {
    return "NETWORK_ERROR";
  }
  if (status === 401) {
    return "UNAUTHORIZED";
  }
  if (status === 403) {
    return "FORBIDDEN";
  }
  if (status === 404) {
    return "RESOURCE_NOT_FOUND";
  }
  if (status === 409) {
    return "CONFLICT";
  }
  if (status === 413) {
    return "UPLOAD_TOO_LARGE";
  }
  if (status === 415) {
    return "UNSUPPORTED_FILE_TYPE";
  }
  if (status === 422) {
    return "VALIDATION_ERROR";
  }
  if (status >= 400 && status < 500) {
    return "BAD_REQUEST";
  }
  return "INTERNAL_ERROR";
}

function fallbackMessageForStatus(status: number, statusText?: string) {
  if (status === 0) {
    return "Unable to connect to the server.";
  }
  if (statusText) {
    return statusText;
  }
  return `Request failed with status ${status}.`;
}

function legacyDetailToError(
  detail: ApiErrorPayload["detail"],
  status: number,
  requestId: string | null,
  statusText?: string
) {
  if (typeof detail === "string") {
    return new ApiError({
      status,
      code: fallbackCodeForStatus(status),
      message: detail,
      requestId
    });
  }

  if (detail && typeof detail === "object") {
    const code =
      typeof detail.code === "string"
        ? detail.code
        : typeof detail.error_code === "string"
          ? detail.error_code
          : fallbackCodeForStatus(status);
    const message =
      typeof detail.message === "string"
        ? detail.message
        : typeof detail.detail === "string"
          ? detail.detail
          : fallbackMessageForStatus(status, statusText);
    const details = Object.fromEntries(
      Object.entries(detail).filter(
        ([key]) => !["code", "error_code", "message", "detail"].includes(key)
      )
    );

    return new ApiError({
      status,
      code,
      message,
      details: Object.keys(details).length > 0 ? details : null,
      requestId
    });
  }

  return null;
}

export async function parseApiErrorResponse(response: Response): Promise<ApiError> {
  const requestId = response.headers.get("X-Request-ID");
  let payload: ApiErrorPayload | null = null;

  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    payload = null;
  }

  if (payload?.error) {
    return new ApiError({
      status: response.status,
      code: payload.error.code || fallbackCodeForStatus(response.status),
      message:
        payload.error.message ||
        fallbackMessageForStatus(response.status, response.statusText),
      details: payload.error.details ?? null,
      requestId: payload.error.request_id ?? requestId
    });
  }

  const legacyError = legacyDetailToError(
    payload?.detail,
    response.status,
    requestId,
    response.statusText
  );
  if (legacyError) {
    return legacyError;
  }

  return new ApiError({
    status: response.status,
    code: fallbackCodeForStatus(response.status),
    message: fallbackMessageForStatus(response.status, response.statusText),
    requestId
  });
}

export function createNetworkApiError(message: string) {
  return new ApiError({
    status: 0,
    code: "NETWORK_ERROR",
    message: message || "Unable to connect to the server."
  });
}

export function normalizeErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    return error.message || fallback;
  }
  if (error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}
