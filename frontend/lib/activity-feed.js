export function initActivityFeed() {
  var container = document.getElementById("activity-toasts");
  if (!container) return;
  var isAnon = document.body.dataset.authenticated !== "true";
  var signupUrl = document.body.dataset.signupUrl;
  var showActivity = document.body.dataset.showActivity === "true";
  if (!showActivity) return;

  function fadeOut(el, delay) {
    setTimeout(function () {
      el.classList.add("animate-slide-out-left");
      el.addEventListener("animationend", function () {
        el.remove();
      });
    }, delay);
  }

  var observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      m.addedNodes.forEach(function (node) {
        if (node.nodeType !== 1) return;
        if (node.classList.contains("activity-toast--nudge")) return;
        fadeOut(node, 6000);

        if (isAnon && signupUrl && !sessionStorage.getItem("activity_nudge_shown")) {
          sessionStorage.setItem("activity_nudge_shown", "1");
          setTimeout(function () {
            var nudge = document.createElement("a");
            nudge.href = signupUrl;
            nudge.className =
              "activity-toast activity-toast--nudge animate-slide-in-left";
            nudge.setAttribute("role", "status");
            nudge.innerHTML =
              '<p class="activity-toast-message">Want to control these notifications? <span class="text-accent font-semibold">Create a free account</span></p>';
            container.appendChild(nudge);
            fadeOut(nudge, 8000);
          }, 7000);
        }
      });
    });
  });
  observer.observe(container, { childList: true });
}
