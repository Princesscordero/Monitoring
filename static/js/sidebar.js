document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const storageKey = "energy-dashboard-sidebar-collapsed";

  if (!sidebar || !sidebarToggle) {
    return;
  }

  function applySidebarState(collapsed) {
    sidebar.classList.toggle("is-collapsed", collapsed);
    sidebarToggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
    sidebarToggle.setAttribute("title", collapsed ? "Expand sidebar" : "Collapse sidebar");
  }

  const savedState = localStorage.getItem(storageKey);
  applySidebarState(savedState !== "false");

  sidebarToggle.addEventListener("click", () => {
    const collapsed = !sidebar.classList.contains("is-collapsed");
    applySidebarState(collapsed);
    localStorage.setItem(storageKey, String(collapsed));
  });
});
