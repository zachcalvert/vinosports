export function initCsrf() {
  document.body.addEventListener("htmx:configRequest", function (e) {
    var csrfCookie = document.cookie
      .split("; ")
      .find(function (c) {
        return c.startsWith("csrftoken=");
      });
    if (csrfCookie) {
      e.detail.headers["X-CSRFToken"] = csrfCookie.split("=")[1];
    }
  });
}
