// Marks the page when it runs inside the portal frame so platform-theme.css can hide each agent's own import entry.
(function () {
  try {
    if (window.self !== window.top) document.documentElement.classList.add("in-platform");
  } catch (e) {
    document.documentElement.classList.add("in-platform");
  }
})();
