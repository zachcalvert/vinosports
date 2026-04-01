export function initLocalTimes() {
  function convertLocalTimes() {
    document.querySelectorAll("time.local-time").forEach(function (el) {
      var iso = el.getAttribute("datetime");
      if (!iso) return;
      var d = new Date(iso);
      if (isNaN(d)) return;
      el.textContent = d.toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
      });
    });
  }
  convertLocalTimes();
  document.body.addEventListener("htmx:afterSwap", convertLocalTimes);
}
