export function showToast(message) {
  var container = document.getElementById("notifications");
  if (!container) return;
  var toast = document.createElement("div");
  toast.className = "toast-shell animate-slide-in";
  toast.setAttribute("role", "alert");
  toast.innerHTML =
    '<svg class="w-5 h-5 text-danger flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></svg>' +
    '<p class="toast-message">' +
    message +
    "</p>" +
    '<button onclick="var t=this.closest(\'[role=alert]\');t.classList.add(\'animate-slide-out\');t.addEventListener(\'animationend\',function(){t.remove()})" class="toast-dismiss"><svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg></button>';
  container.appendChild(toast);
  setTimeout(function () {
    toast.classList.add("animate-slide-out");
    toast.addEventListener("animationend", function () {
      toast.remove();
    });
  }, 5000);
}

export function initToasts() {
  document.body.addEventListener("htmx:responseError", function () {
    showToast("Something went wrong. Please try again.");
  });
  document.body.addEventListener("htmx:sendError", function () {
    showToast("Network error. Check your connection.");
  });
}
