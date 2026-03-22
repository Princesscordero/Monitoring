document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector(".port-page");
    if (!page) {
        return;
    }

    const portId = page.dataset.portId;
    const portName = page.dataset.portName || portId.toUpperCase();

    const statusLargeEl = document.getElementById("portStatusLarge");
    const connectionBadgeEl = document.getElementById("connectionBadge");
    const portSummaryEl = document.getElementById("portSummary");
    const modeTextEl = document.getElementById("modeText");
    const portPowerValueEl = document.getElementById("portPowerValue");
    const portCurrentValueEl = document.getElementById("portCurrentValue");
    const portVoltageValueEl = document.getElementById("portVoltageValue");
    const portEnergyValueEl = document.getElementById("portEnergyValue");
    const sessionDurationValueEl = document.getElementById("sessionDurationValue");
    const dataSourceValueEl = document.getElementById("dataSourceValue");
    const startButton = document.getElementById("startButton");
    const stopButton = document.getElementById("stopButton");
    const manualButton = document.getElementById("manualButton");
    const toastStack = document.getElementById("toastStack");
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

    let manualEnabled = true;
    let alertsEnabled = true;
    const seenNotifications = new Set();

    function formatValue(value, unit) {
        return `${Number(value || 0).toFixed(2)} ${unit}`;
    }

    async function loadSettings() {
        try {
            const response = await fetch("/api/settings");
            const settings = await response.json();
            alertsEnabled = !!settings.alerts_enabled;
        } catch {
            alertsEnabled = true;
        }
    }

    function pushToast(severity, title, message, dedupeKey) {
        if (!toastStack || !alertsEnabled) return;
        if (dedupeKey && seenNotifications.has(dedupeKey)) return;
        if (dedupeKey) seenNotifications.add(dedupeKey);

        const toast = document.createElement("div");
        toast.className = `toast toast-${severity}`;
        toast.innerHTML = `<strong>${title}</strong><p>${message}</p>`;
        toastStack.appendChild(toast);

        setTimeout(() => toast.classList.add("toast-visible"), 10);
        setTimeout(() => {
            toast.classList.remove("toast-visible");
            setTimeout(() => toast.remove(), 220);
        }, 4200);
    }

    function formatDuration(sessionStart) {
        if (!sessionStart) {
            return "00:00:00";
        }

        const elapsedSeconds = Math.max(0, Math.floor(Date.now() / 1000 - Number(sessionStart)));
        const hours = String(Math.floor(elapsedSeconds / 3600)).padStart(2, "0");
        const minutes = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, "0");
        const seconds = String(elapsedSeconds % 60).padStart(2, "0");
        return `${hours}:${minutes}:${seconds}`;
    }

    function updateSummary(port, isEsp32Online) {
        const connectedText = port.connected ? "Device connected" : "No device connected";
        const sourceText = isEsp32Online ? "ESP32 live feed" : "Simulation feed";

        connectionBadgeEl.textContent = connectedText;
        connectionBadgeEl.className = `port-badge ${port.connected ? "connected" : "disconnected"}`;

        if (port.status === "CHARGING") {
            portSummaryEl.textContent = `${portName} is charging at ${formatValue(port.power, "W")} from the ${sourceText.toLowerCase()}.`;
        } else if (!port.connected) {
            portSummaryEl.textContent = `${portName} is waiting for a device. ${sourceText} is online.`;
        } else {
            portSummaryEl.textContent = `${portName} is idle and ready. ${sourceText} is online.`;
        }
    }

    function updateMetricCards(port, isEsp32Online) {
        portPowerValueEl.textContent = formatValue(port.power, "W");
        portCurrentValueEl.textContent = formatValue(port.current, "A");
        portVoltageValueEl.textContent = formatValue(port.voltage, "V");
        portEnergyValueEl.textContent = formatValue(port.session_wh, "Wh");
        sessionDurationValueEl.textContent = formatDuration(port.session_start);
        dataSourceValueEl.textContent = isEsp32Online ? "ESP32" : "Simulated";
    }

    function renderManualUI() {
        manualButton.textContent = manualEnabled ? "Manual: ON" : "Manual: OFF";
        modeTextEl.textContent = manualEnabled
            ? "Manual enabled (Admin can Start/Stop)"
            : "Auto-only mode";
    }

    async function sendPortCommand(command, options = {}) {
        const response = await fetch(`/port/${portId}/${command}`, {
            method: "POST",
            headers: {
                "X-CSRF-Token": csrfToken,
                ...(options.headers || {})
            },
            ...options
        });
        return response.json();
    }

    async function startPort() {
        const out = await sendPortCommand("start");
        if (!out.ok) {
            alert(out.error || "Failed to start");
            return;
        }
        await refresh();
    }

    async function stopPort() {
        const out = await sendPortCommand("stop");
        if (!out.ok) {
            alert(out.error || "Failed to stop");
            return;
        }
        await refresh();
    }

    async function toggleManual() {
        const out = await sendPortCommand("manual", {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: !manualEnabled })
        });

        if (!out.ok) {
            alert(out.error || "Failed to change mode");
            return;
        }

        manualEnabled = !!out.manual_enabled;
        renderManualUI();
        await refresh();
    }

    async function refresh() {
        const response = await fetch("/data");
        const data = await response.json();
        const port = data?.ports?.[portId];

        if (!port) {
            return;
        }

        statusLargeEl.textContent = port.status || "--";
        manualEnabled = !!port.manual_enabled;
        renderManualUI();
        updateSummary(port, !!data.esp32_online);
        updateMetricCards(port, !!data.esp32_online);

        if (!port.connected) {
            pushToast("warning", `${portName} disconnected`, "No device is connected to this port.", `${portId}-disconnected`);
        } else if (port.status === "CHARGING") {
            pushToast("success", `${portName} charging`, `Live output is ${Number(port.power || 0).toFixed(2)} W.`, `${portId}-charging-${Math.floor(Number(port.power || 0) * 10)}`);
        }

        if (Number(data.battery || 0) <= 20) {
            pushToast("critical", "Low battery", `System battery is at ${Number(data.battery || 0).toFixed(1)}%.`, `port-battery-${Math.floor(Number(data.battery || 0))}`);
        }
    }

    startButton.addEventListener("click", startPort);
    stopButton.addEventListener("click", stopPort);
    manualButton.addEventListener("click", toggleManual);

    loadSettings();
    renderManualUI();
    refresh().catch((error) => console.error("Port data refresh failed", error));
    setInterval(() => {
        refresh().catch((error) => console.error("Port data refresh failed", error));
    }, 1000);
});
