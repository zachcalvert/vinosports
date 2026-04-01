// HTMX — separate module ensures window.htmx is set before vendor extensions run
import "./lib/htmx-init.js";

// HTMX extensions (vendored, reference global htmx)
import "./vendor/htmx-ext-ws.js";
import "./vendor/htmx-ext-head-support.js";

// Shared utilities
import { initCsrf } from "./lib/csrf.js";
import { initToasts } from "./lib/toasts.js";
import { initActivityFeed } from "./lib/activity-feed.js";
import { initLocalTimes } from "./lib/local-times.js";

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", function () {
  initCsrf();
  initToasts();
  initActivityFeed();
  initLocalTimes();
});
