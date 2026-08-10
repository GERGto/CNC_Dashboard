// Shared plumbing for the pages that run inside the dashboard iframes:
// finding the backend, talking to the parent window and reading JSON.

// The backend lives on its own port. A query parameter can override both the
// full origin and just the port, which keeps the pages usable standalone.
export function createApiBase() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("apiBase");
  if (fromQuery) {
    try {
      return new URL(fromQuery).origin;
    } catch (_error) {
      // Ignore an invalid override and fall back to host based resolution.
    }
  }

  const base = new URL(window.location.href);
  base.port = params.get("backendPort") || "8080";
  base.pathname = "";
  base.search = "";
  base.hash = "";
  return base.origin;
}

export function postToParent(message) {
  window.parent.postMessage(message, location.origin);
}

// Messages from any other origin are ignored: the pages act on what they
// receive, so a foreign frame must not be able to drive the machine UI.
export function onParentMessage(handler) {
  window.addEventListener("message", (event) => {
    if (event.origin !== location.origin) {
      return;
    }
    const message = event.data;
    if (!message || typeof message !== "object") {
      return;
    }
    handler(message, event);
  });
}

export async function fetchJson(apiBase, path) {
  const response = await fetch(`${apiBase}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}
