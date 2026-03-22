
/*

window.openSettings = function () {
  const modal = document.getElementById("settingsModal");
  if (!modal) return console.error("❌ settingsModal not found");
  modal.classList.remove("hidden");
};

window.closeSettings = function () {
  const modal = document.getElementById("settingsModal");
  if (!modal) return;
  modal.classList.add("hidden");
};

window.saveSettings = function () {
  const intervalEl = document.getElementById("updateIntervalSec");
  const cutoffEl = document.getElementById("cutoff");
  const sessionEl = document.getElementById("session");
  const autoStartEl = document.getElementById("autoStart");

  if (!intervalEl || !cutoffEl || !sessionEl || !autoStartEl) {
    console.error("❌ Missing inputs in settings modal");
    return;
  }

  const interval = Number(intervalEl.value || 2);
  const cutoff = Number(cutoffEl.value || 20);
  const session = Number(sessionEl.value || 60);
  const autoStart = autoStartEl.checked;

  localStorage.setItem(
    "dashboardSettings",
    JSON.stringify({ interval, cutoff, session, autoStart })
  );

  // Restart polling if your dashboard.js provides this
  if (typeof window.restartPolling === "function") window.restartPolling();

  window.closeSettings();
};

document.addEventListener("DOMContentLoaded", () => {
  // hook buttons (your HTML uses these exact IDs)
  const closeBtn = document.getElementById("closeSettingsBtn");
  const saveBtn = document.getElementById("saveSettingsBtn");
  const modal = document.getElementById("settingsModal");

  if (closeBtn) closeBtn.addEventListener("click", window.closeSettings);
  if (saveBtn) saveBtn.addEventListener("click", window.saveSettings);

  // click backdrop to close
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) window.closeSettings();
    });
  }

  // load saved settings into inputs
  const saved = localStorage.getItem("dashboardSettings");
  if (saved) {
    try {
      const s = JSON.parse(saved);
      if (s.interval) document.getElementById("updateIntervalSec").value = s.interval;
      if (s.cutoff) document.getElementById("cutoff").value = s.cutoff;
      if (s.session) document.getElementById("session").value = s.session;
      if (typeof s.autoStart === "boolean") document.getElementById("autoStart").checked = s.autoStart;
    } catch {}
  }
});

*/