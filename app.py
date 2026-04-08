from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    url_for,
    jsonify,
    make_response
)
from werkzeug.security import check_password_hash
import random
import csv
import json
import io
import os
import secrets
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_dotenv_file(path=".env"):
    env_path = path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if not key:
                    continue

                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    value = value[1:-1]

                os.environ.setdefault(key, value)
    except OSError:
        pass


load_dotenv_file()

# ==========================
# APP SETUP
# ==========================

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_SECURE_COOKIES", "").lower() in {"1", "true", "yes"},
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=64 * 1024
)

# ==========================
# ADMIN CREDENTIALS
# ==========================

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = (
    os.environ.get("ADMIN_PASSWORD_HASH")
    or
    "scrypt:32768:8:1$RKCPu0yAieqvD4Nb$"
    "67c554370328ade87eb18e39fd1b0d0bdfc5da0376dcd0190cf1fbe801603ba2797c68f045967728c53b5336bee125d24f26cca5e48ba7fe6f655921eebf86e4"
)

# ==========================
# SYSTEM STATE
# ==========================

battery = 50.0
charging = False
battery_history = []
system_history = []

# ==========================
# REAL-TIME UPDATE INTERVALS (seconds)
# ==========================
SYS_METRICS_INTERVAL = 5        # power/voltage/frequency update every 5s
BATTERY_INTERVAL = 5            # battery update every 5s
PORT_ELECTRICAL_INTERVAL = 2    # port current/power update every 2s
CONNECTION_TOGGLE_INTERVAL = 30 # device plug/unplug toggle every 30s

# ==========================
# SYSTEM SETTINGS
# ==========================

settings = {
    "low_battery_cutoff": 20,
    "max_session_minutes": 60,
    "auto_start_on_connect": False,

    "enable_esp32": True,
    "esp32_ttl": 6,

    "metrics_interval": 5,
    "battery_interval": 5,
    "port_interval": 2,
    "connection_toggle_interval": 30,

    "alerts_enabled": True
}





# ==========================
# CACHED SYSTEM VALUES
# ==========================
system_cache = {
    "power": 0.0,
    "voltage": 12.0,
    "frequency": 90.0,
    "last_metrics_update": time.time(),
    "last_battery_update": time.time(),
}

ports = {
    "p1": {"connected": True, "status": "IDLE", "current": 0.0, "power": 0.0,
           "session_start": None, "session_wh": 0.0, "last_update": time.time(),
           "manual_enabled": True,
           "last_electrical_update": time.time(),
           "last_toggle": time.time(),
           "voltage": 12.0},

    "p2": {"connected": True, "status": "IDLE", "current": 0.0, "power": 0.0,
           "session_start": None, "session_wh": 0.0, "last_update": time.time(),
           "manual_enabled": True,
           "last_electrical_update": time.time(),
           "last_toggle": time.time(),
           "voltage": 12.0},

    "p3": {"connected": True, "status": "IDLE", "current": 0.0, "power": 0.0,
           "session_start": None, "session_wh": 0.0, "last_update": time.time(),
           "manual_enabled": True,
           "last_electrical_update": time.time(),
           "last_toggle": time.time(),
           "voltage": 12.0},
}

# ==========================
# ESP32 LIVE DATA BUFFER
# ==========================
ESP32_API_KEY = os.environ.get("ESP32_API_KEY", "CHANGE_THIS_TO_A_SECRET_KEY")
ESP32_TTL_SECONDS = 6  # if no data for 6s, treat ESP32 as OFFLINE

esp32_last = {
    "timestamp": 0,
    "payload": None
}

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_DISCOVERY_DOC = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_ALLOWED_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("GOOGLE_ALLOWED_EMAILS", "").split(",")
    if email.strip()
}
RECAPTCHA_SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY", "").strip()
RECAPTCHA_SECRET_KEY = os.environ.get("RECAPTCHA_SECRET_KEY", "").strip()
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_ATTEMPTS = 5
login_attempts = {}


def is_admin_logged_in():
    return session.get("admin_logged_in")


def get_client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf():
    expected_token = session.get("csrf_token")
    provided_token = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
        or (request.get_json(silent=True) or {}).get("csrf_token")
    )
    return bool(expected_token and provided_token and secrets.compare_digest(expected_token, provided_token))


def prune_login_attempts(now=None):
    now = now or time.time()
    for ip, attempts in list(login_attempts.items()):
        fresh_attempts = [ts for ts in attempts if now - ts <= LOGIN_WINDOW_SECONDS]
        if fresh_attempts:
            login_attempts[ip] = fresh_attempts
        else:
            login_attempts.pop(ip, None)


def is_login_rate_limited(ip_address):
    now = time.time()
    prune_login_attempts(now)
    return len(login_attempts.get(ip_address, [])) >= LOGIN_MAX_ATTEMPTS


def record_login_failure(ip_address):
    now = time.time()
    attempts = login_attempts.setdefault(ip_address, [])
    attempts.append(now)
    prune_login_attempts(now)


def clear_login_failures(ip_address):
    login_attempts.pop(ip_address, None)


@app.context_processor
def inject_security_context():
    return {
        "csrf_token": get_csrf_token()
    }


@app.before_request
def enforce_security_controls():
    session.permanent = True

    if request.method == "POST" and request.endpoint not in {"esp32_ingest"}:
        if not validate_csrf():
            return jsonify({"ok": False, "error": "Invalid CSRF token"}), 400


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net https://www.google.com https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://www.gstatic.com; "
        "font-src 'self' data:; "
        "connect-src 'self' https://accounts.google.com https://www.google.com; "
        "frame-src https://www.google.com https://www.gstatic.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'; "
        "form-action 'self' https://accounts.google.com"
    )
    return response


def fetch_json(url, data=None, headers=None):
    request_headers = headers or {}
    payload = None
    if data is not None:
        payload = urllib.parse.urlencode(data).encode("utf-8")

    request = urllib.request.Request(url, data=payload, headers=request_headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_google_config():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return None

    try:
        return fetch_json(GOOGLE_DISCOVERY_DOC)
    except Exception:
        return None


def get_google_redirect_uri():
    return url_for("google_callback", _external=True)


def verify_recaptcha(response_token, remote_ip=None):
    if not RECAPTCHA_SECRET_KEY:
        return True, []

    if not response_token:
        return False, ["missing-input-response"]

    try:
        payload = {
            "secret": RECAPTCHA_SECRET_KEY,
            "response": response_token
        }
        if remote_ip:
            payload["remoteip"] = remote_ip

        result = fetch_json(
            "https://www.google.com/recaptcha/api/siteverify",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        return bool(result.get("success")), result.get("error-codes", [])
    except Exception:
        return False, ["verification-failed"]


def google_login_enabled():
    return bool(GOOGLE_ALLOWED_EMAILS) and get_google_config() is not None


def get_data_source_label():
    now = time.time()
    esp32_online = (
        settings.get("enable_esp32", True)
        and
        esp32_last["payload"] is not None
        and (now - esp32_last["timestamp"]) <= settings.get("esp32_ttl", ESP32_TTL_SECONDS)
    )
    return "ESP32 Live" if esp32_online else "Simulation"


def append_system_history(power_value, voltage_value, frequency_value):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {
        "time": timestamp,
        "power": round(power_value, 2),
        "voltage": round(voltage_value, 2),
        "frequency": round(frequency_value, 1),
        "battery": round(battery, 1)
    }

    if not system_history or any(system_history[-1][key] != entry[key] for key in ("power", "voltage", "frequency", "battery")):
        system_history.append(entry)
        if len(system_history) > 180:
            del system_history[:-180]


def build_report_summary():
    active_ports = [
        pid for pid, port in ports.items()
        if port.get("status") == "CHARGING" and port.get("connected")
    ]
    connected_ports = [
        pid for pid, port in ports.items()
        if port.get("connected")
    ]

    peak_battery = max((row["battery"] for row in battery_history), default=round(battery, 1))
    lowest_battery = min((row["battery"] for row in battery_history), default=round(battery, 1))
    average_battery = (
        round(sum(row["battery"] for row in battery_history) / len(battery_history), 1)
        if battery_history else round(battery, 1)
    )
    peak_port_power = max((port.get("power", 0.0) for port in ports.values()), default=0.0)
    total_session_energy = round(sum(port.get("session_wh", 0.0) for port in ports.values()), 2)
    recent_power_points = system_history[-12:]
    peak_output_entry = max(system_history, key=lambda row: row["power"], default=None)
    battery_start = battery_history[0]["battery"] if battery_history else round(battery, 1)
    battery_end = battery_history[-1]["battery"] if battery_history else round(battery, 1)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_source": get_data_source_label(),
        "system": {
            "power": round(system_cache.get("power", 0.0), 2),
            "voltage": round(system_cache.get("voltage", 0.0), 2),
            "frequency": round(system_cache.get("frequency", 0.0), 1),
            "battery": round(battery, 1),
            "charging": charging
        },
        "highlights": {
            "active_ports": len(active_ports),
            "connected_ports": len(connected_ports),
            "peak_port_power": round(peak_port_power, 2),
            "total_session_energy": total_session_energy,
            "average_battery": average_battery,
            "peak_battery": peak_battery,
            "lowest_battery": lowest_battery,
            "history_points": len(battery_history)
        },
        "graph_insights": {
            "power_samples": len(system_history),
            "battery_change": round(battery_end - battery_start, 1),
            "peak_output": peak_output_entry["power"] if peak_output_entry else round(system_cache.get("power", 0.0), 2),
            "peak_output_time": peak_output_entry["time"] if peak_output_entry else datetime.now().strftime("%H:%M:%S"),
            "recent_power_points": recent_power_points
        },
        "ports": {
            pid: {
                "connected": port.get("connected", False),
                "status": port.get("status", "IDLE"),
                "power": round(port.get("power", 0.0), 2),
                "current": round(port.get("current", 0.0), 2),
                "voltage": round(port.get("voltage", 0.0), 2),
                "session_wh": round(port.get("session_wh", 0.0), 2),
                "manual_enabled": port.get("manual_enabled", True)
            }
            for pid, port in ports.items()
        }
    }


def build_readable_report_text(report):
    lines = [
        "ENERGY HARVESTING SYSTEM REPORT",
        "=" * 32,
        "",
        f"Generated: {report['generated_at']}",
        f"Data Source: {report['data_source']}",
        "",
        "SYSTEM OVERVIEW",
        "-" * 15,
        f"Power Output: {report['system']['power']:.2f} W",
        f"Voltage: {report['system']['voltage']:.2f} V",
        f"Vibration Frequency: {report['system']['frequency']:.1f} Hz",
        f"Battery Level: {report['system']['battery']:.1f}%",
        f"Charging State: {'Charging' if report['system']['charging'] else 'Idle'}",
        "",
        "HIGHLIGHTS",
        "-" * 10,
        f"Active Ports: {report['highlights']['active_ports']}",
        f"Connected Ports: {report['highlights']['connected_ports']}",
        f"Peak Port Power: {report['highlights']['peak_port_power']:.2f} W",
        f"Total Session Energy: {report['highlights']['total_session_energy']:.2f} Wh",
        f"Average Battery: {report['highlights']['average_battery']:.1f}%",
        f"Peak Battery: {report['highlights']['peak_battery']:.1f}%",
        f"Lowest Battery: {report['highlights']['lowest_battery']:.1f}%",
        f"Battery History Points: {report['highlights']['history_points']}",
        "",
        "PORT STATUS",
        "-" * 11,
    ]

    for port_id, port in report["ports"].items():
        lines.extend([
            f"{port_id.upper()}",
            f"  Connection: {'Connected' if port['connected'] else 'Disconnected'}",
            f"  Status: {port['status']}",
            f"  Power: {port['power']:.2f} W",
            f"  Current: {port['current']:.2f} A",
            f"  Voltage: {port['voltage']:.2f} V",
            f"  Session Energy: {port['session_wh']:.2f} Wh",
            f"  Manual Mode: {'Enabled' if port['manual_enabled'] else 'Disabled'}",
            "",
        ])

    graph = report.get("graph_insights", {})
    if graph:
        lines.extend([
            "GRAPH INSIGHTS",
            "-" * 14,
            f"Power Samples Captured: {graph.get('power_samples', 0)}",
            f"Battery Change Over History: {graph.get('battery_change', 0):.1f}%",
            f"Peak Output Recorded: {graph.get('peak_output', 0):.2f} W at {graph.get('peak_output_time', '--:--:--')}",
            "",
            "RECENT POWER TREND",
            "-" * 18,
        ])

        recent_points = graph.get("recent_power_points", [])
        if recent_points:
            for point in recent_points:
                lines.append(
                    f"{point['time']}  |  {point['power']:.2f} W  |  {point['voltage']:.2f} V  |  {point['frequency']:.1f} Hz  |  {point['battery']:.1f}%"
                )
        else:
            lines.append("No recent power history available yet.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _pdf_escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_pdf(title, lines):
    page_width = 612
    page_height = 792
    left_margin = 54
    top_margin = 64
    line_height = 16
    max_lines_per_page = 42

    pages = [lines[i:i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)] or [[]]
    objects = []

    def add_object(data):
        objects.append(data)
        return len(objects)

    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    content_ids = []

    for page_lines in pages:
        stream_lines = [
            "BT",
            f"/F1 18 Tf {left_margin} {page_height - top_margin} Td ({_pdf_escape(title)}) Tj",
            "/F1 11 Tf",
        ]

        current_y = page_height - top_margin - 28
        for line in page_lines:
            safe_line = _pdf_escape(str(line))
            stream_lines.append(f"1 0 0 1 {left_margin} {current_y} Tm ({safe_line}) Tj")
            current_y -= line_height

        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", "replace")
        content_id = add_object(
            f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream"
        )
        content_ids.append(content_id)
        page_ids.append(None)

    pages_id = add_object("")

    for idx, content_id in enumerate(content_ids):
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids[idx] = page_id

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>"
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_id, obj_data in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_id} 0 obj\n".encode("latin-1"))
        pdf.extend(obj_data.encode("latin-1"))
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("latin-1")
    )
    return bytes(pdf)

# ==========================
# AUTH ROUTES
# ==========================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        client_ip = get_client_ip()
        if is_login_rate_limited(client_ip):
            error = "Too many login attempts. Please wait a few minutes and try again."
            return render_template(
                "login.html",
                error=error,
                google_login_enabled=google_login_enabled(),
                recaptcha_site_key=RECAPTCHA_SITE_KEY
            ), 429

        recaptcha_ok, recaptcha_errors = verify_recaptcha(
            request.form.get("g-recaptcha-response"),
            request.remote_addr
        )
        if not recaptcha_ok:
            error = "reCAPTCHA verification failed. Please try again."
            return render_template(
                "login.html",
                error=error,
                google_login_enabled=google_login_enabled(),
                recaptcha_site_key=RECAPTCHA_SITE_KEY
            )

        username = request.form["username"]
        password = request.form["password"]

        if (
            username == ADMIN_USERNAME
            and check_password_hash(ADMIN_PASSWORD_HASH, password)
        ):
            session["admin_logged_in"] = True
            session["admin_email"] = username
            clear_login_failures(client_ip)
            return redirect(url_for("home"))
        else:
            record_login_failure(client_ip)
            error = "Invalid username or password"

    return render_template(
        "login.html",
        error=error,
        google_login_enabled=google_login_enabled(),
        recaptcha_site_key=RECAPTCHA_SITE_KEY
    )


@app.route("/auth/google")
def google_login():
    google_config = get_google_config()
    if not google_config:
        return redirect(url_for("login"))

    state = secrets.token_urlsafe(24)
    session["google_oauth_state"] = state

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": get_google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account"
    }
    auth_url = f'{google_config["authorization_endpoint"]}?{urllib.parse.urlencode(params)}'
    return redirect(auth_url)


@app.route("/auth/google/callback")
def google_callback():
    google_config = get_google_config()
    if not google_config:
        return redirect(url_for("login"))

    state = request.args.get("state")
    if not state or state != session.pop("google_oauth_state", None):
        return redirect(url_for("login"))

    if request.args.get("error"):
        return redirect(url_for("login"))

    code = request.args.get("code")
    if not code:
        return redirect(url_for("login"))

    try:
        token_data = fetch_json(
            google_config["token_endpoint"],
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": get_google_redirect_uri(),
                "grant_type": "authorization_code"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        userinfo = fetch_json(
            google_config["userinfo_endpoint"],
            headers={"Authorization": f'Bearer {token_data["access_token"]}'}
        )
    except Exception:
        return redirect(url_for("login"))

    email = (userinfo.get("email") or "").lower()
    email_verified = bool(userinfo.get("email_verified"))
    if not email_verified or (GOOGLE_ALLOWED_EMAILS and email not in GOOGLE_ALLOWED_EMAILS):
        return redirect(url_for("login"))

    session["admin_logged_in"] = True
    session["admin_email"] = email
    clear_login_failures(get_client_ip())
    return redirect(url_for("home"))

@app.route("/port/<port_id>/start", methods=["POST"])
def start_port(port_id):
    global battery

    if not is_admin_logged_in():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    if port_id not in ports:
        return jsonify({"ok": False, "error": "Invalid port"}), 404

    port = ports[port_id]

    # system rules before allowing manual start
    if not port["connected"]:
        return jsonify({"ok": False, "error": "No device connected"}), 400

    if not port["manual_enabled"]:
        return jsonify({"ok": False, "error": "Port is set to Auto-only (manual disabled)"}), 400

    if battery <= settings.get("low_battery_cutoff", 20):
        return jsonify({"ok": False, "error": "Battery too low to start charging"}), 400

    # start charging
    port["status"] = "CHARGING"
    port["session_start"] = time.time()
    port["session_wh"] = 0.0
    port["last_update"] = time.time()

    return jsonify({"ok": True, "message": f"{port_id} started"})

@app.route("/port/<port_id>/stop", methods=["POST"])
def stop_port(port_id):
    if not is_admin_logged_in():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    if port_id not in ports:
        return jsonify({"ok": False, "error": "Invalid port"}), 404

    port = ports[port_id]

    #VALIDATION CHECKS
    if not port["connected"]:
        return jsonify({"ok": False, "error": "No device connected"}), 400

    if port["status"] != "CHARGING":
        return jsonify({"ok": False, "error": "Port is not charging"}), 400

    #ONLY RUN IF VALID
    port["status"] = "IDLE"
    port["current"] = 0.0
    port["power"] = 0.0
    port["session_start"] = None
    port["last_update"] = time.time()

    return jsonify({"ok": True, "message": f"{port_id} stopped"})

@app.route("/port/<port_id>/manual", methods=["POST"])
def toggle_manual(port_id):
    if not is_admin_logged_in():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    if port_id not in ports:
        return jsonify({"ok": False, "error": "Invalid port"}), 404

    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", True))

    ports[port_id]["manual_enabled"] = enabled

    return jsonify({"ok": True, "manual_enabled": enabled})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/esp32/ingest", methods=["POST"])
def esp32_ingest():
    api_key = request.headers.get("X-API-KEY")
    if api_key != ESP32_API_KEY:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    # Minimal fields expected from ESP32
    required = ["voltage", "frequency", "battery", "ports"]
    for k in required:
        if k not in data:
            return jsonify({"ok": False, "error": f"Missing field: {k}"}), 400

    if not isinstance(data["ports"], dict):
        return jsonify({"ok": False, "error": "ports must be object"}), 400

    for pid in ["p1", "p2", "p3"]:
        if pid not in data["ports"]:
            return jsonify({"ok": False, "error": f"Missing ports.{pid}"}), 400

        p = data["ports"][pid]
        for pk in ["connected", "current", "power"]:
            if pk not in p:
                return jsonify({"ok": False, "error": f"Missing ports.{pid}.{pk}"}), 400

    # Store latest
    esp32_last["timestamp"] = time.time()
    esp32_last["payload"] = data

    return jsonify({"ok": True})

# ==========================
# DASHBOARD
# ==========================

@app.route("/")
def home():
    if not is_admin_logged_in():
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/port1")
def port1_page():
    if not is_admin_logged_in():
        return redirect(url_for("login"))
    return render_template("port1.html")

@app.route("/port2")
def port2_page():
    if not is_admin_logged_in():
        return redirect(url_for("login"))
    return render_template("port2.html")

@app.route("/port3")
def port3_page():
    if not is_admin_logged_in():
        return redirect(url_for("login"))
    return render_template("port3.html")

@app.route("/api/settings", methods=["GET", "POST"])
def manage_settings():
    if not is_admin_logged_in():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    if request.method == "GET":
        return jsonify(settings)

    data = request.get_json(silent=True) or {}

    numeric_ranges = {
        "low_battery_cutoff": (5, 50),
        "max_session_minutes": (5, 180),
        "esp32_ttl": (1, 60),
        "metrics_interval": (1, 30),
        "battery_interval": (1, 30),
        "port_interval": (1, 20),
        "connection_toggle_interval": (5, 120)
    }

    for key, value in data.items():
        if key not in settings:
            continue

        if key in numeric_ranges:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": f"Invalid value for {key}"}), 400

            minimum, maximum = numeric_ranges[key]
            settings[key] = max(minimum, min(maximum, parsed))
            continue

        if key in {"auto_start_on_connect", "enable_esp32", "alerts_enabled"}:
            settings[key] = bool(value)

    return jsonify({"ok": True, "settings": settings})

# ==========================
# LIVE DATA API (REAL TIME-BASED)
# ==========================

def simulate_connection_toggle(port, interval=CONNECTION_TOGGLE_INTERVAL):
    now = time.time()

    # toggle only after interval seconds
    if now - port.get("last_toggle", now) >= interval:
        port["connected"] = not port["connected"]
        port["last_toggle"] = now

    # if unplugged → cut off power + stop session
    if not port["connected"]:
        port["status"] = "NO_DEVICE"
        port["current"] = 0.0
        port["power"] = 0.0
        port["session_start"] = None

@app.route("/data")
def data():
    global battery, charging, system_cache

    now = time.time()

    use_esp32 = (
        settings.get("enable_esp32", True)
        and
        esp32_last["payload"] is not None
        and (now - esp32_last["timestamp"]) <= settings.get("esp32_ttl", ESP32_TTL_SECONDS)
    )

    # --------------------------
    # ✅ CASE 1: ESP32 ONLINE
    # --------------------------
    if use_esp32:
        live = esp32_last["payload"]

        # override system metrics
        system_cache["voltage"] = float(live["voltage"])
        system_cache["frequency"] = float(live["frequency"])
        battery = float(live["battery"])

        # power optional (compute if missing)
        if "power" in live:
            system_cache["power"] = float(live["power"])
        else:
            system_cache["power"] = sum(
                float(live["ports"][pid]["power"]) for pid in ["p1", "p2", "p3"]
            )

        append_system_history(
            system_cache["power"],
            system_cache["voltage"],
            system_cache["frequency"]
        )

        # update ports from ESP32
        for pid in ["p1", "p2", "p3"]:
            p = ports[pid]
            esp_p = live["ports"][pid]

            p["connected"] = bool(esp_p["connected"])

            if not p["connected"]:
                p["status"] = "NO_DEVICE"
                p["current"] = 0.0
                p["power"] = 0.0
                p["session_start"] = None
            else:
                p["current"] = float(esp_p["current"])
                p["power"] = float(esp_p["power"])
                p["voltage"] = system_cache["voltage"]

                # If manual OFF, status follows power
                if not p["manual_enabled"]:
                    p["status"] = "CHARGING" if p["power"] > 0 else "IDLE"

        # return ESP32 data (no simulation overwrite)
        return jsonify({
            "power": system_cache["power"],
            "voltage": system_cache["voltage"],
            "frequency": system_cache["frequency"],
            "battery": round(battery, 1),
            "charging": charging,
            "ports": ports,
            "esp32_online": True
        })

    # --------------------------
    # ✅ CASE 2: ESP32 OFFLINE (SIMULATION)
    # --------------------------

    # 1) SYSTEM METRICS (timed)
    metrics_interval = settings.get("metrics_interval", SYS_METRICS_INTERVAL)
    battery_interval = settings.get("battery_interval", BATTERY_INTERVAL)
    port_interval = settings.get("port_interval", PORT_ELECTRICAL_INTERVAL)
    connection_toggle_interval = settings.get("connection_toggle_interval", CONNECTION_TOGGLE_INTERVAL)
    low_battery_cutoff = settings.get("low_battery_cutoff", 20)
    max_session_seconds = settings.get("max_session_minutes", 60) * 60

    if now - system_cache["last_metrics_update"] >= metrics_interval:
        system_cache["power"] = round(random.uniform(1.0, 6.0), 2)
        system_cache["voltage"] = round(random.uniform(11.5, 13.0), 2)
        system_cache["frequency"] = round(random.uniform(80, 100), 1)
        system_cache["last_metrics_update"] = now

    power = system_cache["power"]
    voltage = system_cache["voltage"]
    frequency = system_cache["frequency"]
    append_system_history(power, voltage, frequency)

    # 2) BATTERY (timed)
    if now - system_cache["last_battery_update"] >= battery_interval:
        if battery <= 19:
            charging = True
        if battery >= 100:
            charging = False

        if charging:
            battery += 1.2
        else:
            battery -= 0.6

        battery = max(0, min(100, battery))

        battery_history.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "battery": round(battery, 1)
        })

        system_cache["last_battery_update"] = now

    # 3) PORTS (timed simulation)
    for pid, port in ports.items():
        simulate_connection_toggle(port, interval=connection_toggle_interval)

        dt = now - port.get("last_update", now)
        port["last_update"] = now

        # AUTO STOP rules
        if not port["connected"] and port["status"] == "CHARGING":
            port["status"] = "NO_DEVICE"
            port["current"] = 0.0
            port["power"] = 0.0
            port["session_start"] = None

        if battery <= low_battery_cutoff and port["status"] == "CHARGING":
            port["status"] = "IDLE"
            port["current"] = 0.0
            port["power"] = 0.0
            port["session_start"] = None

        if (
            port["status"] == "CHARGING"
            and port.get("session_start")
            and (now - port["session_start"]) >= max_session_seconds
        ):
            port["status"] = "IDLE"
            port["current"] = 0.0
            port["power"] = 0.0
            port["session_start"] = None

        if now - port.get("last_electrical_update", now) >= port_interval:
            if port["status"] == "CHARGING" and port["connected"]:
                port["voltage"] = round(random.uniform(11.5, 13.0), 2)
                port["current"] = round(random.uniform(0.6, 2.2), 2)
                port["power"] = round(port["voltage"] * port["current"], 2)
            else:
                port["current"] = 0.0
                port["power"] = 0.0
                if (
                    settings.get("auto_start_on_connect")
                    and port["connected"]
                    and port["manual_enabled"]
                    and port["status"] == "IDLE"
                    and battery > low_battery_cutoff
                ):
                    port["status"] = "CHARGING"
                    port["session_start"] = now
                if port["connected"] and port["status"] == "NO_DEVICE":
                    port["status"] = "IDLE"

            port["last_electrical_update"] = now

        if port["status"] == "CHARGING" and port["connected"]:
            port["session_wh"] += (port["power"] * dt) / 3600.0

    return jsonify({
        "power": power,
        "voltage": voltage,
        "frequency": frequency,
        "battery": round(battery, 1),
        "charging": charging,
        "ports": ports,
        "esp32_online": False
    })

# ==========================
# EXPORT CSV
# ==========================

@app.route("/api/reports/summary")
def report_summary():
    if not is_admin_logged_in():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    return jsonify({"ok": True, "report": build_report_summary()})


@app.route("/export")
def export_csv():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    export_type = request.args.get("type", "battery")
    export_format = request.args.get("format", "csv")

    if export_type == "battery":
        return redirect(url_for("export_battery_history"))

    if export_type == "ports":
        return redirect(url_for("export_ports_snapshot"))

    if export_type == "report":
        if export_format == "json":
            return redirect(url_for("export_report_json"))
        if export_format == "pdf":
            return redirect(url_for("export_report_pdf"))
        if export_format == "txt":
            return redirect(url_for("export_report_text"))
        return redirect(url_for("export_report_csv"))

    return redirect(url_for("export_battery_history"))


@app.route("/export/battery-history.csv")
def export_battery_history():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Time", "Battery (%)"])
    for row in battery_history:
        writer.writerow([row["time"], row["battery"]])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=battery_history.csv"
    response.headers["Content-Type"] = "text/csv"

    return response


@app.route("/export/ports.csv")
def export_ports_snapshot():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Port",
        "Connected",
        "Status",
        "Power (W)",
        "Current (A)",
        "Voltage (V)",
        "Session Energy (Wh)",
        "Manual Enabled"
    ])

    for port_id, port in ports.items():
        writer.writerow([
            port_id,
            port.get("connected"),
            port.get("status"),
            round(port.get("power", 0.0), 2),
            round(port.get("current", 0.0), 2),
            round(port.get("voltage", 0.0), 2),
            round(port.get("session_wh", 0.0), 2),
            port.get("manual_enabled")
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=ports_snapshot.csv"
    response.headers["Content-Type"] = "text/csv"
    return response


@app.route("/export/report.json")
def export_report_json():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    report = build_report_summary()
    response = make_response(json.dumps(report, indent=2))
    response.headers["Content-Disposition"] = "attachment; filename=energy_report.json"
    response.headers["Content-Type"] = "application/json"
    return response


@app.route("/export/report.txt")
def export_report_text():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    report = build_report_summary()
    response = make_response(build_readable_report_text(report))
    response.headers["Content-Disposition"] = "attachment; filename=energy_report.txt"
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@app.route("/export/report.pdf")
def export_report_pdf():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    report = build_report_summary()
    lines = build_readable_report_text(report).splitlines()
    pdf_bytes = build_simple_pdf("Energy Harvesting System Report", lines[2:])
    response = make_response(pdf_bytes)
    response.headers["Content-Disposition"] = "attachment; filename=energy_report.pdf"
    response.headers["Content-Type"] = "application/pdf"
    return response


@app.route("/export/report.csv")
def export_report_csv():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    report = build_report_summary()
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Section", "Metric", "Value"])
    writer.writerow(["system", "generated_at", report["generated_at"]])
    writer.writerow(["system", "data_source", report["data_source"]])

    for key, value in report["system"].items():
        writer.writerow(["system", key, value])

    for key, value in report["highlights"].items():
        writer.writerow(["highlights", key, value])

    for port_id, port_data in report["ports"].items():
        for key, value in port_data.items():
            writer.writerow([port_id, key, value])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=energy_report.csv"
    response.headers["Content-Type"] = "text/csv"
    return response

# ==========================
# RUN
# ==========================

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"})
