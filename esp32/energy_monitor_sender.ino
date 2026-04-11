#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_INA219.h>

// ================= WIFI =================
const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASSWORD";

// Replace with your computer's local IP address running Flask.
const char* flaskServer = "http://192.168.1.100:5000/api/esp32/ingest";
const char* apiKey = "CHANGE_THIS_TO_A_SECRET_KEY";

// ================= OLED =================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ================= SENSOR =================
Adafruit_INA219 ina219;

// ================= PINS =================
#define COIN_PIN 15
#define BTN1 32
#define BTN2 33
#define BTN3 25
#define RELAY1 26
#define RELAY2 27
#define RELAY3 14

// ================= VARIABLES =================
long t1 = 0, t2 = 0, t3 = 0;
int selectedPort = 1;
bool coinDetected = false;

unsigned long lastTimer = 0;
unsigned long lastSend = 0;
const unsigned long SEND_INTERVAL_MS = 2000;

float batteryPercent = 75.0;   // Replace with a real battery reading if available.
float vibrationFrequency = 90.0; // Replace with a real vibration/frequency sensor if available.

void connectWiFi() {
  WiFi.begin(ssid, password);

  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Connecting WiFi...");
  display.display();

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }

  display.clearDisplay();
  display.setCursor(0, 0);
  display.println("WiFi Connected");
  display.println(WiFi.localIP());
  display.display();
  delay(1500);
}

void updateTimers() {
  if (millis() - lastTimer < 1000) {
    return;
  }

  lastTimer = millis();
  if (t1 > 0) t1--;
  if (t2 > 0) t2--;
  if (t3 > 0) t3--;
}

void updateSelectedPort() {
  if (!digitalRead(BTN1)) selectedPort = 1;
  if (!digitalRead(BTN2)) selectedPort = 2;
  if (!digitalRead(BTN3)) selectedPort = 3;
}

void detectCoin() {
  if (digitalRead(COIN_PIN) == HIGH && !coinDetected) {
    coinDetected = true;

    if (selectedPort == 1) t1 += 600;
    if (selectedPort == 2) t2 += 600;
    if (selectedPort == 3) t3 += 600;

    Serial.println("Coin inserted");
  }

  if (digitalRead(COIN_PIN) == LOW) {
    coinDetected = false;
  }
}

void updateRelays() {
  digitalWrite(RELAY1, t1 > 0 ? HIGH : LOW);
  digitalWrite(RELAY2, t2 > 0 ? HIGH : LOW);
  digitalWrite(RELAY3, t3 > 0 ? HIGH : LOW);
}

void drawDisplay(float voltage, float currentA) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);

  display.println("Charging Station");
  display.print("P1: "); display.print(t1); display.println("s");
  display.print("P2: "); display.print(t2); display.println("s");
  display.print("P3: "); display.print(t3); display.println("s");
  display.print("Sel: P"); display.println(selectedPort);
  display.print("V: "); display.print(voltage, 2); display.println("V");
  display.print("I: "); display.print(currentA, 2); display.println("A");
  display.print("Bat: "); display.print(batteryPercent, 1); display.println("%");

  display.display();
}

void sendToFlask(float voltage, float currentA) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    return;
  }

  float p1Current = t1 > 0 ? currentA : 0.0;
  float p2Current = t2 > 0 ? currentA : 0.0;
  float p3Current = t3 > 0 ? currentA : 0.0;

  float p1Power = t1 > 0 ? voltage * p1Current : 0.0;
  float p2Power = t2 > 0 ? voltage * p2Current : 0.0;
  float p3Power = t3 > 0 ? voltage * p3Current : 0.0;

  StaticJsonDocument<768> doc;
  doc["voltage"] = voltage;
  doc["frequency"] = vibrationFrequency;
  doc["battery"] = batteryPercent;
  doc["power"] = p1Power + p2Power + p3Power;

  JsonObject ports = doc.createNestedObject("ports");

  JsonObject p1 = ports.createNestedObject("p1");
  p1["connected"] = t1 > 0;
  p1["current"] = p1Current;
  p1["power"] = p1Power;
  p1["voltage"] = voltage;
  p1["status"] = t1 > 0 ? "CHARGING" : "IDLE";

  JsonObject p2 = ports.createNestedObject("p2");
  p2["connected"] = t2 > 0;
  p2["current"] = p2Current;
  p2["power"] = p2Power;
  p2["voltage"] = voltage;
  p2["status"] = t2 > 0 ? "CHARGING" : "IDLE";

  JsonObject p3 = ports.createNestedObject("p3");
  p3["connected"] = t3 > 0;
  p3["current"] = p3Current;
  p3["power"] = p3Power;
  p3["voltage"] = voltage;
  p3["status"] = t3 > 0 ? "CHARGING" : "IDLE";

  String body;
  serializeJson(doc, body);

  HTTPClient http;
  http.begin(flaskServer);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-KEY", apiKey);

  int httpCode = http.POST(body);
  String response = http.getString();

  Serial.print("POST code: ");
  Serial.println(httpCode);
  Serial.println(response);

  http.end();
}

void setup() {
  Serial.begin(115200);

  pinMode(COIN_PIN, INPUT);
  pinMode(BTN1, INPUT_PULLUP);
  pinMode(BTN2, INPUT_PULLUP);
  pinMode(BTN3, INPUT_PULLUP);
  pinMode(RELAY1, OUTPUT);
  pinMode(RELAY2, OUTPUT);
  pinMode(RELAY3, OUTPUT);

  digitalWrite(RELAY1, LOW);
  digitalWrite(RELAY2, LOW);
  digitalWrite(RELAY3, LOW);

  Wire.begin();
  ina219.begin();

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED failed");
    while (true) {}
  }

  connectWiFi();
}

void loop() {
  updateSelectedPort();
  detectCoin();
  updateTimers();
  updateRelays();

  float voltage = ina219.getBusVoltage_V();
  float currentA = ina219.getCurrent_mA() / 1000.0;

  drawDisplay(voltage, currentA);

  if (millis() - lastSend >= SEND_INTERVAL_MS) {
    lastSend = millis();
    sendToFlask(voltage, currentA);
  }
}
