# ESP32 Sync Guide

This sketch sends live hardware data from the ESP32 to the Flask dashboard at:

- `/api/esp32/ingest`

## 1. Update the sketch

Open [energy_monitor_sender.ino](/C:/energy_dashboard/esp32/energy_monitor_sender.ino) and replace:

- `YOUR_WIFI`
- `YOUR_PASSWORD`
- `http://192.168.1.100:5000/api/esp32/ingest`
- `CHANGE_THIS_TO_A_SECRET_KEY`

Use your laptop's LAN IP address, not `127.0.0.1`.

## 2. Set the same API key in Flask

From `C:\energy_dashboard`:

```powershell
$env:ESP32_API_KEY="CHANGE_THIS_TO_A_SECRET_KEY"
python app.py
```

The value must exactly match the `apiKey` in the sketch.

## 3. Make sure both devices are on the same network

Your ESP32 and the computer running Flask must use the same Wi-Fi.

## 4. Check whether data is arriving

After logging into the dashboard, open:

- `http://127.0.0.1:5000/api/esp32/status`

If syncing is working, you should see:

- `"online": true`
- the latest normalized payload

## 5. Expected payload shape

The Flask backend accepts:

```json
{
  "voltage": 12.4,
  "frequency": 90.0,
  "battery": 75.0,
  "power": 14.4,
  "ports": {
    "p1": {
      "connected": true,
      "current": 1.2,
      "power": 14.4,
      "voltage": 12.4,
      "status": "CHARGING"
    },
    "p2": {
      "connected": false,
      "current": 0.0,
      "power": 0.0,
      "voltage": 12.4,
      "status": "IDLE"
    },
    "p3": {
      "connected": false,
      "current": 0.0,
      "power": 0.0,
      "voltage": 12.4,
      "status": "IDLE"
    }
  }
}
```

The backend also tolerates common alternative field names, but this is the cleanest format to use.

## 6. Current placeholders in the sketch

The sketch currently uses placeholder values for:

- `batteryPercent`
- `vibrationFrequency`

If you add real sensors later, replace those variables with actual readings before sending.
