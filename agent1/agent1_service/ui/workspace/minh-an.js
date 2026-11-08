"use strict";
const panes = [...document.querySelectorAll("main section")];
function show() {
  const pane = panes.find(p => "#" + p.id === location.hash) || panes[0];
  panes.forEach(p => p.hidden = p !== pane);
  document.querySelectorAll("nav a").forEach(a => {
    if (a.getAttribute("href") === "#" + pane.id) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", show);
document.querySelector("#scenario").onchange = e => {
  document.querySelector("#base").hidden = e.target.value !== "base";
  document.querySelector("#stress").hidden = e.target.value !== "stress";
};
show();
