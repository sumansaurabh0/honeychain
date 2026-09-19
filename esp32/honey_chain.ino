#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <HX711.h>

// const char* ssid = "YOUR_WIFI";
// const char* password = "YOUR_PASSWORD";
// const char* url = "http://YOUR_SERVER_IP:8000/api/sensors";

const char* ssid = "YOUR_ACTUAL_WIFI_NAME";
const char* password = "YOUR_ACTUAL_WIFI_PASSWORD";
const char* url = "http://172.22.77.9:8000/api/sensors";

const uint8_t DHT_PIN = 4;
const uint8_t HX711_DT_PIN = 18;
const uint8_t HX711_SCK_PIN = 19;
const uint8_t GAS_PIN = 39;
const uint8_t MIC_PIN = 34;
const float CALIBRATION_FACTOR = 248.9;

DHT dht(DHT_PIN, DHT11);
HX711 scale;
bool scaleTared = false;

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  for (uint8_t attempts = 0; WiFi.status() != WL_CONNECTED && attempts < 20; attempts++) {
    delay(500);
    Serial.print('.');
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " connected" : " failed");
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  scale.begin(HX711_DT_PIN, HX711_SCK_PIN);
  scale.set_scale(CALIBRATION_FACTOR);
  if (scale.is_ready()) {
    scale.tare();
    scaleTared = true;
  }
  connectWiFi();
}

void loop() {
  connectWiFi();

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  if (isnan(temperature) || isnan(humidity) || temperature < -40 || temperature > 85 || humidity < 0 || humidity > 100) {
    Serial.println("Invalid DHT11 reading; transmission skipped");
    delay(60000);
    return;
  }

  if (!scale.is_ready()) {
    Serial.println("HX711 unavailable; transmission skipped");
    delay(60000);
    return;
  }

  if (!scaleTared) {
    scale.tare();
    scaleTared = true;
  }

  float weight = scale.get_units(5);
  int gasRaw = analogRead(GAS_PIN);
  int micRaw = analogRead(MIC_PIN);
  if (isnan(weight) || weight < 0 || weight > 1000 || gasRaw < 0 || gasRaw > 4095 || micRaw < 0 || micRaw > 4095) {
    Serial.println("Invalid sensor reading; transmission skipped");
    delay(60000);
    return;
  }

  Serial.printf("Temperature: %.1f C, Humidity: %.1f %%, Weight: %.1f g, Gas: %d, Mic: %d\n",
                temperature, humidity, weight, gasRaw, micRaw);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    String body = "{\"hive_id\":\"HIVE001\",\"temperature\":" + String(temperature, 1) +
                  ",\"humidity\":" + String(humidity, 1) + ",\"weight\":" + String(weight, 1) +
                  ",\"gas_raw\":" + String(gasRaw) + ",\"mic_raw\":" + String(micRaw) + "}";
    int status = http.POST(body);
    Serial.printf("HTTP status: %d\n", status);
    http.end();
  } else {
    Serial.println("WiFi unavailable; transmission skipped");
  }

  delay(60000);
}
