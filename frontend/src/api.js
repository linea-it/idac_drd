function getCsrf() {
  const root = document.getElementById("idac-drd-root");
  return root?.dataset?.csrfToken || "";
}

/** Prefixa paths absolutos com SCRIPT_NAME (ex.: /drd em produção). */
export function appUrl(path) {
  if (!path.startsWith("/")) return path;
  const root = document.getElementById("idac-drd-root");
  const prefix = (root?.dataset?.apiPrefix || "").replace(/\/$/, "");
  if (prefix && path.startsWith(`${prefix}/`)) return path;
  return `${prefix}${path}`;
}

async function request(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };
  if (options.body && !(options.body instanceof URLSearchParams)) {
    headers["Content-Type"] = "application/json";
  }
  if (options.method && options.method !== "GET") {
    headers["X-CSRFToken"] = getCsrf();
  }
  const res = await fetch(appUrl(path), {
    credentials: "same-origin",
    ...options,
    headers,
  });
  if (!res.ok) {
    let detail = await res.text();
    try {
      const json = JSON.parse(detail);
      // ValidationError do DRF vira lista quando não é erro de campo
      if (Array.isArray(json)) {
        detail = json.map((x) => (x && x.message) || x).join(" ");
      } else {
        detail = json.detail || JSON.stringify(json);
      }
    } catch {
      /* keep text */
    }
    throw new Error(detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body: JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: (path) => request(path, { method: "DELETE" }),
};
