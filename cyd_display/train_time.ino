#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <SPI.h>
#include <time.h>

TFT_eSPI tft = TFT_eSPI();

// === Touchscreen pins - your working config ===
#define XPT2046_IRQ 36
#define XPT2046_MOSI 32
#define XPT2046_MISO 39
#define XPT2046_CLK 25
#define XPT2046_CS 33

SPIClass touchscreenSPI = SPIClass(VSPI);
XPT2046_Touchscreen touchscreen(XPT2046_CS, XPT2046_IRQ);

// === CONFIG ===
const char* WIFI_SSID = "";
const char* WIFI_PASS = "";
const char* API_HOST = "http://192.168.1.135:8080"; // your Pi

// === CONFIG - Format "CODE:Display Name" ===
const char* ROUTE1_FROM = "SUC:Sutton Common";
const char* ROUTE1_TO = "WIM:Wimbledon";
const char* ROUTE2_FROM = "WIM:Wimbledon";
const char* ROUTE2_TO = "KNG:Kingston";
const char* BUS_STOP = "490020089S:Kimpton Road"; // SMS or Naptan : Human name

// === Screen Rotation - 0=Portait (2=flip), 1=Landscape(3=flip)
// code works with Portait only
const int SCREEN_ORIENTATION = 2;

// === Colour
// Use https://rgbcolorpicker.com/565 to pick
#define COL_BUS_TITLE_BG    0x2807
#define COL_BUS_TITLE_TEXT  TFT_WHITE
#define COL_TRAIN1_TITLE_BG 0x0167
#define COL_TRAIN2_TITLE_BG 0x0007
#define COL_TITLE_TEXT      TFT_WHITE
#define COL_BG              TFT_BLACK
#define COL_ROW_BG          0x1082  // dark grey row

// === BACKLIGHT / POWER ===
#define BACKLIGHT_PIN 21
#define LDR_PIN 34
const int SLEEP_TIMEOUT_MS = 60000;
const int LDR_READ_INTERVAL = 2000;
const int MIN_BRIGHTNESS = 40;
const int MAX_BRIGHTNESS = 255;

unsigned long lastTouch = 0;
unsigned long lastLdrRead = 0;
unsigned long lastFetch = 0;
bool isSleeping = false;
int currentBrightness = 200;

struct Train { String std; String etd; String plat; String dest; bool cancelled; };
struct Bus { String line; String dest; int dueMin; };

String lastUpdatedStr = "--:--";

Train route1[3];
Train route2[3];
Bus buses[4];
int r1Count = 0, r2Count = 0, busCount = 0;

void setBrightness(int b) {
  b = constrain(b, 0, 255);
  currentBrightness = b;
  ledcWrite(BACKLIGHT_PIN, b);
}

void autoBrightness() {
  int ldr = analogRead(LDR_PIN);
  int mapped = map(ldr, 0, 4095, MAX_BRIGHTNESS, MIN_BRIGHTNESS);
  mapped = constrain(mapped, MIN_BRIGHTNESS, MAX_BRIGHTNESS);
  int newB = (currentBrightness * 0.7) + (mapped * 0.3);
  setBrightness(newB);
}

void goToSleep() {
  isSleeping = true;
  tft.fillScreen(TFT_BLACK);
  setBrightness(0);
}

void wakeUp() {
  isSleeping = false;
  setBrightness(150);
  lastTouch = millis();
  lastFetch = 0;
  tft.fillScreen(TFT_BLACK);
  tft.drawCentreString("WAKING...", 120, 140, 4);
  delay(500);
}

// helpers to split "CODE:Name"
String getCode(const char* s) {
  String str = String(s);
  int idx = str.indexOf(':');
  if (idx > 0) return str.substring(0, idx);
  return str;
}

String getName(const char* s) {
  String str = String(s);
  int idx = str.indexOf(':');
  if (idx > 0 && idx < str.length() - 1) return str.substring(idx + 1);
  return str; // fallback to code if no name
}

void fetchBus(const char* stopCombined) {
  String stop = getCode(stopCombined); // decode inside
  String url = String(API_HOST) + "/api/bus?stop=" + stop;
  HTTPClient http;
  http.begin(url);
  http.setTimeout(5000);
  int code = http.GET();
  if (code!= 200) { busCount = 0; http.end(); return; }
  DynamicJsonDocument doc(4096);
  if (deserializeJson(doc, http.getString())) { busCount = 0; http.end(); return; }
  http.end();
  JsonArray arr = doc["arrivals"].as<JsonArray>();
  busCount = 0;
  for (JsonObject b : arr) {
    if (busCount >= 4) break;
    buses[busCount].line = b["line"] | "-";
    buses[busCount].dest = b["destination"] | "";
    buses[busCount].dueMin = b["dueInMin"] | 99;
    busCount++;
  }
}

void fetchRoute(const char* fromCombined, const char* toCombined, Train* storage, int &count) {
  String from = getCode(fromCombined); // decode inside
  String to = getCode(toCombined);
  String url = String(API_HOST) + "/api/trains?from=" + from + "&to=" + to;
  HTTPClient http;
  http.begin(url);
  http.setTimeout(5000);
  int code = http.GET();
  if (code!= 200) { count = 0; http.end(); return; }
  DynamicJsonDocument doc(8192);
  if (deserializeJson(doc, http.getString())) { count = 0; http.end(); return; }
  http.end();
  JsonArray services = doc["services"].as<JsonArray>();
  count = 0;
  for (JsonObject s : services) {
    if (count >= 2) break;
    storage[count].std = s["std"] | "-";
    storage[count].etd = s["etd"] | "-";
    storage[count].plat = s["platform"] | "-";
    storage[count].dest = s["destination"] | "";
    storage[count].cancelled = s["isCancelled"] | false;
    count++;
  }
}

void drawBusSection(int yStart, const char* stopCombined) {
  String displayName = getName(stopCombined); // decode inside
  if (displayName.length() > 20) displayName = displayName.substring(0, 20);
  tft.fillRect(0, yStart, 240, 22, COL_BUS_TITLE_BG);
  tft.setTextColor(COL_BUS_TITLE_TEXT, COL_BUS_TITLE_BG);
  tft.drawString("BUS " + displayName, 10, yStart + 3, 2);
  int y = yStart + 26;
  if (busCount == 0) {
    tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
    tft.drawString("No buses / No data", 10, y, 2);
    return;
  }
  for (int i = 0; i < busCount; i++) {
    tft.fillRect(5, y, 36, 24, TFT_WHITE);
    tft.setTextColor(TFT_BLACK, TFT_WHITE);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(buses[i].line, 23, y+12, 2);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    String dest = buses[i].dest;
    if (dest.length() > 14) dest = dest.substring(0,14);
    tft.drawString(dest, 48, y+2, 2);
    String dueStr;
    uint16_t c = TFT_GREEN;
    if (buses[i].dueMin <= 0) { dueStr = "Due"; c = TFT_GREEN; }
    else if (buses[i].dueMin <= 4) { dueStr = String(buses[i].dueMin) + "m"; c = TFT_YELLOW; }
    else { dueStr = String(buses[i].dueMin) + "m"; c = TFT_WHITE; }
    tft.setTextColor(c, TFT_BLACK);
    tft.drawString(dueStr, 190, y+2, 2);
    y += 28;
  }
}

void drawRouteSection(int idx, const char* fromCombined, const char* toCombined, Train* trains, int count, int yStart, int height) {
  String title = getName(fromCombined) + " -> " + getName(toCombined); // decode inside
  uint16_t titleBg = (idx == 0)? COL_TRAIN1_TITLE_BG : COL_TRAIN2_TITLE_BG;
  tft.fillRect(0, yStart, 240, height, COL_ROW_BG);
  tft.fillRect(0, yStart, 240, 20, titleBg);
  tft.setTextColor(COL_TITLE_TEXT, titleBg);
  tft.drawString(title, 10, yStart + 2, 2);
  int y = yStart + 26;
  if (count == 0) {
    tft.setTextColor(TFT_RED, 0x1082);
    tft.drawString("No data", 10, y, 2);
    return;
  }
  for (int i = 0; i < count; i++) {
    tft.setTextColor(TFT_WHITE, 0x1082);
    tft.drawString(trains[i].std, 8, y, 2);
    uint16_t c = TFT_GREEN;
    if (trains[i].cancelled) c = TFT_RED;
    else if (trains[i].etd!= "On time") c = TFT_YELLOW;
    tft.setTextColor(c, 0x1082);
    tft.drawString(trains[i].etd.substring(0, 10), 70, y, 1);
    tft.setTextColor(TFT_CYAN, 0x1082);
    tft.drawString("P" + trains[i].plat, 190, y, 1);
    y += 24;
  }
}

void drawScreen() {
  tft.fillScreen(TFT_BLACK);
  drawBusSection(0, BUS_STOP);
  drawRouteSection(0, ROUTE1_FROM, ROUTE1_TO, route1, r1Count, 112, 93);
  drawRouteSection(1, ROUTE2_FROM, ROUTE2_TO, route2, r2Count, 207, 93);

  tft.fillRect(0, 300, 240, 20, TFT_BLACK);
  tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
  tft.drawString(String(WiFi.RSSI()) + "dBm", 5, 308, 1);
  tft.setTextColor(TFT_LIGHTGREY, TFT_BLACK);
  tft.drawString("Upd: " + lastUpdatedStr, 130, 308, 1);
}

void setup() {
  Serial.begin(115200);
  tft.init();
  tft.setRotation(SCREEN_ORIENTATION);
  touchscreenSPI.begin(XPT2046_CLK, XPT2046_MISO, XPT2046_MOSI, XPT2046_CS);
  touchscreen.begin(touchscreenSPI);
  touchscreen.setRotation(SCREEN_ORIENTATION);
  pinMode(BACKLIGHT_PIN, OUTPUT);
  analogReadResolution(12);
  ledcAttach(BACKLIGHT_PIN, 5000, 8);
  setBrightness(200);
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString("Connecting WiFi...", 20, 20, 2);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status()!= WL_CONNECTED) delay(500);
  lastTouch = millis();
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  setenv("TZ", "GMT0BST,M3.5.0/1,M10.5.0", 1);
  tzset();
}

void loop() {
  bool touched = false;
  if (touchscreen.tirqTouched() && touchscreen.touched()) {
    touched = true;
    TS_Point p = touchscreen.getPoint();
  }
  if (touched) {
    if (isSleeping) wakeUp();
    lastTouch = millis();
    delay(200);
  }
  if (!isSleeping && millis() - lastTouch > SLEEP_TIMEOUT_MS) goToSleep();
  if (isSleeping) { delay(100); return; }

  if (millis() - lastLdrRead > LDR_READ_INTERVAL) {
    autoBrightness();
    lastLdrRead = millis();
  }
  if (millis() - lastFetch > 30000 || lastFetch == 0) {
    fetchBus(BUS_STOP);
    delay(150);
    fetchRoute(ROUTE1_FROM, ROUTE1_TO, route1, r1Count);
    delay(150);
    fetchRoute(ROUTE2_FROM, ROUTE2_TO, route2, r2Count);

    // get local time
    struct tm timeinfo;
    if (getLocalTime(&timeinfo)) {
      char buf[10];
      strftime(buf, sizeof(buf), "%H:%M:%S", &timeinfo);
      lastUpdatedStr = String(buf);
    } else {
      // fallback if NTP not yet synced
      lastUpdatedStr = String(millis()/1000) + "s";
    }

    drawScreen();
    lastFetch = millis();
  }  
}
