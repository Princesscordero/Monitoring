document.addEventListener("DOMContentLoaded", () => {
  const navItems = document.querySelectorAll(".nav-item");
  const esp = document.getElementById("esp32Status");
  const openSettingsButton = document.getElementById("openSettingsBtn");
  const closeSettingsButton = document.getElementById("closeSettingsBtn");
  const saveSettingsButton = document.getElementById("saveSettingsBtn");
  const settingsModal = document.getElementById("settingsModal");
  const exportForm = document.getElementById("exportForm");
  const exportType = document.getElementById("exportType");
  const exportFormat = document.getElementById("exportFormat");
  const alertsFeed = document.getElementById("alertsFeed");
  const alertsStatus = document.getElementById("alertsStatus");
  const toastStack = document.getElementById("toastStack");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

  function withCsrfHeaders(headers = {}) {
    return {
      ...headers,
      "X-CSRF-Token": csrfToken
    };
  }

  const powerData = {
    labels: [],
    datasets: [{
      label: "Power Output (W)",
      data: [],
      borderColor: "#33d0ff",
      backgroundColor: "rgba(51, 208, 255, 0.14)",
      borderWidth: 2,
      tension: 0.35,
      fill: true
    }]
  };

  const batteryData = {
    labels: [],
    datasets: [{
      label: "Battery Level (%)",
      data: [],
      borderColor: "#8bffb0",
      backgroundColor: "rgba(139, 255, 176, 0.12)",
      borderWidth: 2,
      tension: 0.35,
      fill: true
    }]
  };

  const chartTextColor = "#94a3b8";
  const chartAvailable = typeof Chart !== "undefined";
  const powerCanvas = document.getElementById("powerChart");
  const batteryCanvas = document.getElementById("batteryChart");

  let powerChart = null;
  let batteryChart = null;

  if (chartAvailable && powerCanvas && batteryCanvas) {
    powerChart = new Chart(powerCanvas.getContext("2d"), {
      type: "line",
      data: powerData,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "white" } } },
        scales: {
          x: { ticks: { color: chartTextColor } },
          y: { beginAtZero: true, ticks: { color: chartTextColor } }
        }
      }
    });

    batteryChart = new Chart(batteryCanvas.getContext("2d"), {
      type: "line",
      data: batteryData,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "white" } } },
        scales: {
          x: { ticks: { color: chartTextColor } },
          y: { min: 0, max: 100, ticks: { color: chartTextColor } }
        }
      }
    });
  }

  navItems.forEach((item) => {
    item.addEventListener("click", (event) => {
      event.preventDefault();
      document.querySelector(".view.active").classList.remove("active");
      document.querySelector(".nav-item.active").classList.remove("active");

      const viewName = item.getAttribute("data-view");
      document.getElementById(`view-${viewName}`).classList.add("active");
      item.classList.add("active");
    });
  });

  let soundMuted = false;
  let lowBatteryPlayed = false;
  let lastReportFetch = 0;
  let alertsEnabled = true;
  const seenNotifications = new Set();

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element) {
      element.textContent = value;
    }
  }

  function playLowBatteryBeep() {
    if (soundMuted || !alertsEnabled) return;

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const ctx = new AudioCtx();
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();

    oscillator.type = "sine";
    oscillator.frequency.value = 520;
    gain.gain.value = 0.12;

    oscillator.connect(gain);
    gain.connect(ctx.destination);

    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.6);
  }

  window.toggleMute = function () {
    soundMuted = !soundMuted;
    alert(soundMuted ? "Alerts muted" : "Alerts enabled");
  };

  function pushToast(severity, title, message, dedupeKey) {
    if (!toastStack || !alertsEnabled) return;
    if (dedupeKey && seenNotifications.has(dedupeKey)) return;
    if (dedupeKey) seenNotifications.add(dedupeKey);

    const toast = document.createElement("div");
    toast.className = `toast toast-${severity}`;
    toast.innerHTML = `<strong>${title}</strong><p>${message}</p>`;
    toastStack.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("toast-visible");
    }, 10);

    setTimeout(() => {
      toast.classList.remove("toast-visible");
      setTimeout(() => toast.remove(), 220);
    }, 4200);
  }

  function renderAlerts(alerts) {
    if (!alertsFeed || !alertsStatus) return;

    if (!alerts.length) {
      alertsFeed.innerHTML = `
        <div class="alert-item alert-item-empty">
          <div>
            <strong>No active alerts</strong>
            <p>The system will show warnings and notifications here.</p>
          </div>
        </div>
      `;
      alertsStatus.textContent = alertsEnabled ? "Monitoring" : "Muted";
      alertsStatus.className = `status-pill ${alertsEnabled ? "online" : "offline"}`;
      return;
    }

    alertsFeed.innerHTML = alerts.map((item) => `
      <div class="alert-item alert-item-${item.severity}">
        <div>
          <strong>${item.title}</strong>
          <p>${item.message}</p>
        </div>
        <span>${item.tag}</span>
      </div>
    `).join("");

    const highestSeverity = alerts.some((item) => item.severity === "critical")
      ? "critical"
      : alerts.some((item) => item.severity === "warning")
        ? "warning"
        : "info";
    alertsStatus.textContent = `${alerts.length} Active`;
    alertsStatus.className = `status-pill alert-pill-${highestSeverity}`;
  }

  function buildAlerts(data) {
    const alerts = [];
    const cutoff = Number(document.getElementById("setLowBattery")?.value || 20);

    if (!data.esp32_online) {
      alerts.push({
        severity: "info",
        title: "Simulation mode active",
        message: "ESP32 data is offline, so the dashboard is running on simulated values.",
        tag: "Source"
      });
    }

    if (Number(data.battery || 0) <= cutoff) {
      alerts.push({
        severity: "critical",
        title: "Low battery protection threshold reached",
        message: `Battery is at ${Number(data.battery || 0).toFixed(1)}%, which is at or below the ${cutoff}% cutoff.`,
        tag: "Battery"
      });
      pushToast(
        "critical",
        "Low battery",
        `Battery level dropped to ${Number(data.battery || 0).toFixed(1)}%.`,
        `battery-low-${Math.floor(Number(data.battery || 0))}`
      );
    }

    Object.entries(data.ports || {}).forEach(([portId, port]) => {
      if (!port.connected) {
        alerts.push({
          severity: "warning",
          title: `${portId.toUpperCase()} disconnected`,
          message: "No device is currently connected to this port.",
          tag: "Port"
        });
      }

      if (port.status === "CHARGING") {
        pushToast(
          "success",
          `${portId.toUpperCase()} charging`,
          `Output is active at ${Number(port.power || 0).toFixed(2)} W.`,
          `${portId}-charging-${Math.floor(Number(port.power || 0) * 10)}`
        );
      }
    });

    return alerts;
  }

  function syncExportFormatOptions() {
    if (!exportType || !exportFormat) return;

    const reportSelected = exportType.value === "report";
    const jsonOption = Array.from(exportFormat.options).find((option) => option.value === "json");
    const txtOption = Array.from(exportFormat.options).find((option) => option.value === "txt");
    const pdfOption = Array.from(exportFormat.options).find((option) => option.value === "pdf");

    if (jsonOption) {
      jsonOption.disabled = !reportSelected;
    }

    if (txtOption) {
      txtOption.disabled = !reportSelected;
    }

    if (pdfOption) {
      pdfOption.disabled = !reportSelected;
    }

    if (!reportSelected && ["json", "txt", "pdf"].includes(exportFormat.value)) {
      exportFormat.value = "csv";
    }
  }

  function setPort(prefix, port) {
    if (!port) return;

    const statusEl = document.getElementById(prefix + "Status");
    if (!port.connected) {
      statusEl.innerText = "NO DEVICE";
      document.getElementById(prefix + "Power").innerText = "0.00 W";
      document.getElementById(prefix + "Current").innerText = "0.00 A";
      statusEl.className = "port-status disabled";
      return;
    }

    statusEl.innerText = port.status;
    document.getElementById(prefix + "Power").innerText = Number(port.power || 0).toFixed(2) + " W";
    document.getElementById(prefix + "Current").innerText = Number(port.current || 0).toFixed(2) + " A";

    statusEl.className = "port-status";
    if (port.status === "CHARGING") statusEl.classList.add("charging");
    else statusEl.classList.add("idle");
  }

  function renderReport(report) {
    if (!report) return;

    setText("reportDataSource", report.data_source || "--");
    setText("reportAverageBattery", `${Number(report.highlights?.average_battery || 0).toFixed(1)}%`);
    setText("reportPeakPortPower", `${Number(report.highlights?.peak_port_power || 0).toFixed(2)} W`);
    setText("reportTotalEnergy", `${Number(report.highlights?.total_session_energy || 0).toFixed(2)} Wh`);
    setText("reportGeneratedAt", report.generated_at || "--");
    setText("reportActivePorts", String(report.highlights?.active_ports ?? 0));
    setText("reportConnectedPorts", String(report.highlights?.connected_ports ?? 0));
    setText("reportPeakBattery", `${Number(report.highlights?.peak_battery || 0).toFixed(1)}%`);
    setText("reportLowestBattery", `${Number(report.highlights?.lowest_battery || 0).toFixed(1)}%`);
    setText("reportHistoryPoints", String(report.highlights?.history_points ?? 0));

    const portList = document.getElementById("reportPortList");
    if (!portList) return;

    const portEntries = Object.entries(report.ports || {});
    if (!portEntries.length) {
      portList.innerHTML = '<div class="report-port-item"><span>No port data available.</span></div>';
      return;
    }

    portList.innerHTML = portEntries.map(([portId, port]) => `
      <div class="report-port-item">
        <div>
          <strong>${portId.toUpperCase()}</strong>
          <p>${port.connected ? "Connected" : "Disconnected"} • ${port.status}</p>
        </div>
        <div class="report-port-metrics">
          <span>${Number(port.power || 0).toFixed(2)} W</span>
          <span>${Number(port.current || 0).toFixed(2)} A</span>
          <span>${Number(port.session_wh || 0).toFixed(2)} Wh</span>
        </div>
      </div>
    `).join("");
  }

  async function fetchReportSummary(force = false) {
    const now = Date.now();
    if (!force && now - lastReportFetch < 5000) {
      return;
    }

    const response = await fetch("/api/reports/summary");
    const payload = await response.json();
    if (!payload.ok) {
      return;
    }

    renderReport(payload.report);
    lastReportFetch = now;
  }

  async function fetchData() {
    const response = await fetch("/data");
    const data = await response.json();

    document.getElementById("power").innerText = Number(data.power || 0).toFixed(2) + " W";
    document.getElementById("voltage").innerText = Number(data.voltage || 0).toFixed(2) + " V";
    document.getElementById("frequency").innerText = Number(data.frequency || 0).toFixed(1) + " Hz";
    document.getElementById("heroPower").innerText = Number(data.power || 0).toFixed(2) + " W";
    document.getElementById("heroBattery").innerText = Number(data.battery || 0).toFixed(1) + "%";

    const batteryLevel = document.getElementById("batteryLevel");
    const batteryText = document.getElementById("batteryPercent");
    const batteryStatus = document.getElementById("batteryStatus");
    const batteryHealth = document.getElementById("batteryHealth");

    batteryLevel.style.width = data.battery + "%";
    batteryText.innerText = Number(data.battery || 0).toFixed(1) + "%";
    batteryLevel.className = "battery-level";

    if (data.battery >= 100) {
      batteryLevel.classList.add("battery-good");
      batteryHealth.innerText = "Full";
    } else if (data.battery > 60) {
      batteryLevel.classList.add("battery-good");
      batteryHealth.innerText = "Optimal";
    } else if (data.battery > 30) {
      batteryLevel.classList.add("battery-medium");
      batteryHealth.innerText = "Moderate";
    } else {
      batteryLevel.classList.add("battery-low", "low-battery");
      batteryHealth.innerText = "Low";
    }

    if (data.battery >= 100) {
      batteryStatus.innerText = `Fully charged • ${Number(data.voltage || 0).toFixed(2)} V`;
    } else if (data.charging) {
      batteryStatus.innerText = `Charging • ${Number(data.voltage || 0).toFixed(2)} V`;
    } else {
      batteryStatus.innerText = `Discharging • ${Number(data.voltage || 0).toFixed(2)} V`;
    }

    if (data.charging) {
      batteryLevel.classList.add("charging");
    }

    if (data.ports) {
      setPort("p1", data.ports.p1);
      setPort("p2", data.ports.p2);
      setPort("p3", data.ports.p3);

      const activePorts = [data.ports.p1, data.ports.p2, data.ports.p3]
        .filter((port) => port && port.status === "CHARGING").length;
      document.getElementById("heroActivePorts").innerText = `${activePorts} / 3`;
    }

    const time = new Date().toLocaleTimeString();
    if (powerChart) {
      powerData.labels.push(time);
      powerData.datasets[0].data.push(data.power);
      if (powerData.labels.length > 20) {
        powerData.labels.shift();
        powerData.datasets[0].data.shift();
      }
      powerChart.update();
    }

    if (batteryChart) {
      batteryData.labels.push(time);
      batteryData.datasets[0].data.push(data.battery);
      if (batteryData.labels.length > 30) {
        batteryData.labels.shift();
        batteryData.datasets[0].data.shift();
      }
      batteryChart.update();
    }

    if (data.battery <= 20) {
      document.body.classList.add("low-battery-warning");
      if (!lowBatteryPlayed) {
        playLowBatteryBeep();
        lowBatteryPlayed = true;
      }
    } else {
      document.body.classList.remove("low-battery-warning");
      lowBatteryPlayed = false;
    }

    if (esp) {
      esp.innerText = data.esp32_online ? "ESP32 Live" : "Simulation Mode";
      esp.className = `status-pill ${data.esp32_online ? "online" : "offline"}`;
    }

    renderAlerts(buildAlerts(data));

    await fetchReportSummary();
  }

  fetchData().catch((error) => console.error("Dashboard data refresh failed", error));
  setInterval(() => {
    fetchData().catch((error) => console.error("Dashboard data refresh failed", error));
  }, 1000);

  async function loadSettings() {
    const res = await fetch("/api/settings");
    const s = await res.json();

    const setIfPresent = (id, value, prop = "value") => {
      const element = document.getElementById(id);
      if (!element) return;
      element[prop] = value;
    };

    setIfPresent("setLowBattery", s.low_battery_cutoff);
    setIfPresent("setMaxSession", s.max_session_minutes);
    setIfPresent("setAutoStart", s.auto_start_on_connect, "checked");
    setIfPresent("setEnableEsp32", !!s.enable_esp32, "checked");
    setIfPresent("setEsp32Ttl", s.esp32_ttl);
    setIfPresent("setMetricsInterval", s.metrics_interval);
    setIfPresent("setBatteryInterval", s.battery_interval);
    setIfPresent("setPortInterval", s.port_interval);
    setIfPresent("setConnectionToggleInterval", s.connection_toggle_interval ?? 30);
    setIfPresent("setAlertsEnabled", !!s.alerts_enabled, "checked");
    setIfPresent("setLightMode", (window.getAppTheme?.() || "dark") === "light", "checked");
    alertsEnabled = !!s.alerts_enabled;
  }

  async function saveSettings() {
    const readNumber = (id, fallback) => {
      const element = document.getElementById(id);
      return element ? parseInt(element.value, 10) : fallback;
    };

    const readChecked = (id, fallback) => {
      const element = document.getElementById(id);
      return element ? element.checked : fallback;
    };

    const payload = {
      low_battery_cutoff: readNumber("setLowBattery", 20),
      max_session_minutes: readNumber("setMaxSession", 60),
      auto_start_on_connect: readChecked("setAutoStart", false),
      enable_esp32: readChecked("setEnableEsp32", true),
      esp32_ttl: readNumber("setEsp32Ttl", 6),
      metrics_interval: readNumber("setMetricsInterval", 5),
      battery_interval: readNumber("setBatteryInterval", 5),
      port_interval: readNumber("setPortInterval", 2),
      connection_toggle_interval: readNumber("setConnectionToggleInterval", 30),
      alerts_enabled: readChecked("setAlertsEnabled", true)
    };

    await fetch("/api/settings", {
      method: "POST",
      headers: withCsrfHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload)
    });

    const selectedTheme = readChecked("setLightMode", false) ? "light" : "dark";
    window.setAppTheme?.(selectedTheme);

    alert("Settings saved!");
    alertsEnabled = payload.alerts_enabled;
    closeSettings();
  }

  function closeSettings() {
    if (settingsModal) {
      settingsModal.style.display = "none";
      settingsModal.classList.add("hidden");
    }
  }

  window.openSettings = () => {
    if (!settingsModal) return;
    settingsModal.style.display = "flex";
    settingsModal.classList.remove("hidden");
    loadSettings();
  };

  window.saveSettings = saveSettings;
  window.closeSettings = closeSettings;

  if (closeSettingsButton) {
    closeSettingsButton.addEventListener("click", closeSettings);
  }

  if (openSettingsButton) {
    openSettingsButton.addEventListener("click", window.openSettings);
  }

  if (saveSettingsButton) {
    saveSettingsButton.addEventListener("click", saveSettings);
  }

  if (settingsModal) {
    settingsModal.addEventListener("click", (event) => {
      if (event.target === settingsModal) {
        closeSettings();
      }
    });
  }

  if (exportType) {
    exportType.addEventListener("change", syncExportFormatOptions);
    syncExportFormatOptions();
  }

  if (exportForm) {
    exportForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const type = exportType ? exportType.value : "battery";
      const format = exportFormat ? exportFormat.value : "csv";
      window.location.href = `/export?type=${encodeURIComponent(type)}&format=${encodeURIComponent(format)}`;
    });
  }

  window.exportCSV = () => {
    window.location.href = "/export";
  };
});
