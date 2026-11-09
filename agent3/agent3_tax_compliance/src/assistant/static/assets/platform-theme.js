// Shared portal context for embedded agents and their standalone pages.
(function () {
  try {
    if (window.self !== window.top) document.documentElement.classList.add("in-platform");
  } catch (e) {
    document.documentElement.classList.add("in-platform");
  }

  function setupPortalReturn() {
    const links = document.querySelectorAll("[data-portal-return]");
    if (!links.length) return;
    let origin = new URLSearchParams(location.search).get("portal");
    if (!origin && document.documentElement.dataset.agent === "4") origin = location.origin;
    try {
      if (!origin) origin = sessionStorage.getItem("kt-portal-origin") || sessionStorage.getItem("agent1-portal-origin");
      const portal = new URL(origin);
      if (portal.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(portal.hostname) ||
          portal.username || portal.password || (portal.origin === location.origin && document.documentElement.dataset.agent !== "4")) return;
      for (const link of links) {
        link.href = portal.origin + "/#overview";
        link.hidden = false;
      }
      try { sessionStorage.setItem("kt-portal-origin", portal.origin); } catch (e) { /* private mode */ }
    } catch (e) { /* Independently opened agents may have no portal context. */ }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setupPortalReturn, { once: true });
  else setupPortalReturn();
})();
