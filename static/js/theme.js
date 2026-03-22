document.addEventListener("DOMContentLoaded", () => {
  const themeToggle = document.getElementById("themeToggle");
  const themeToggleLabel = themeToggle?.querySelector(".nav-label");
  const storageKey = "energy-dashboard-theme";
  const preferredTheme = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  const savedTheme = localStorage.getItem(storageKey) || preferredTheme;

  function applyTheme(theme) {
    document.body.setAttribute("data-theme", theme);
    if (themeToggle) {
      const label = theme === "light" ? "Dark Mode" : "Light Mode";
      if (themeToggleLabel) {
        themeToggleLabel.textContent = label;
      } else {
        themeToggle.textContent = label;
      }
    }
  }

  applyTheme(savedTheme);

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const nextTheme = document.body.getAttribute("data-theme") === "light" ? "dark" : "light";
      localStorage.setItem(storageKey, nextTheme);
      applyTheme(nextTheme);
    });
  }
});
