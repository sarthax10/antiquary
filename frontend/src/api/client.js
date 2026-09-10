// The only file in this app that calls fetch() directly — every page/component goes
// through the feature modules in this folder instead. Keeps the CSRF-header and
// credentials boilerplate in one place (see docs/ARCHITECTURE.md).

let csrfTokenPromise = null;

function fetchCsrfToken() {
  if (!csrfTokenPromise) {
    csrfTokenPromise = fetch("/api/auth/csrf", { credentials: "include" })
      .then((res) => res.json())
      .then((data) => data.csrf_token);
  }
  return csrfTokenPromise;
}

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (method !== "GET") {
    headers["X-CSRFToken"] = await fetchCsrfToken();
  }

  const res = await fetch(path, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.error || `Request failed (${res.status})`, res.status, data);
  }
  return data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
};
