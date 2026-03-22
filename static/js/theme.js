document.addEventListener("DOMContentLoaded", () => {
  const themeToggle = document.getElementById("themeToggle");
  const storageKey = "energy-dashboard-theme";
  const preferredTheme = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  const savedTheme = localStorage.getItem(storageKey) || preferredTheme;

  function applyTheme(theme) {
    document.body.setAttribute("data-theme", theme);
    if (themeToggle) {
      themeToggle.textContent = theme === "light" ? "Dark Mode" : "Light Mode";
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
