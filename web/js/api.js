// Every call to the backend goes through here.
//
// Cookies carry the session (HttpOnly, so JS cannot read or leak the token), which
// is why `credentials: "same-origin"` is set on all of them.

const BASE = "/api";

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    credentials: "same-origin",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  });

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json().catch(() => ({}))
    : await response.text();

  if (!response.ok) {
    const detail =
      (body && (body.detail || body.message)) ||
      (typeof body === "string" && body) ||
      `Request failed (${response.status})`;
    const error = new Error(detail);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

const json = (method) => (path, payload) =>
  request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const api = {
  me: () => request("/me"),
  state: () => request("/state"),
  leaderboard: (showdown) =>
    request(showdown ? `/leaderboard?showdown=${encodeURIComponent(showdown)}` : "/leaderboard"),
  showdowns: () => request("/showdowns"),
  logout: () => request("/auth/logout", { method: "POST" }),

  submit(file) {
    const form = new FormData();
    form.append("file", file, file.name);
    return request("/submit", { method: "POST", body: form });
  },

  admin: {
    settings: () => request("/admin/settings"),
    update: json("PATCH").bind(null, "/admin/settings"),
    // `kind` labels the run: practice (the clock), mock, or final. It decides
    // whether the board survives the next practice run and which previous board
    // a balanced or finals iteration seeds on, see server/scheduler.py.
    runNow: (kind = "practice", variations = null) =>
      json("POST")("/admin/run-now", variations ? { kind, variations } : { kind }),
    submissions: () => request("/admin/submissions"),
    showdowns: () => request("/admin/showdowns"),
    deleteShowdown: (id) =>
      request(`/admin/showdowns/${encodeURIComponent(id)}`, { method: "DELETE" }),
    audit: () => request("/admin/audit"),
    ban: (roll, banned) =>
      json("POST")("/admin/ban", { roll, banned }),
  },
};

/**
 * Live leaderboard stream.
 *
 * EventSource reconnects on its own, but only for transport drops, if the
 * server is restarted mid-deploy it can sit in a failed state, so a failure is
 * escalated to the caller and the caller falls back to polling.
 */
export function openStream({
  onLeaderboard,
  onSchedule,
  onState,
  onProgress,
  onShowdown,
  onError,
}) {
  let source;
  try {
    source = new EventSource(`${BASE}/leaderboard/stream`, { withCredentials: true });
  } catch {
    onError?.();
    return () => {};
  }

  const bind = (name, handler) =>
    handler &&
    source.addEventListener(name, (event) => {
      try {
        handler(JSON.parse(event.data));
      } catch {
        /* keepalive frames and partial writes are not worth surfacing */
      }
    });

  bind("leaderboard", onLeaderboard);
  bind("schedule", onSchedule);
  // Published whenever an admin changes a setting, so a variation switched off
  // in the control room disappears from every open tab without a reload.
  bind("state", onState);
  bind("progress", onProgress);
  bind("showdown", onShowdown);
  source.addEventListener("error", () => onError?.());

  return () => source.close();
}
