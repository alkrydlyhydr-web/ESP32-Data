#include <WiFi.h>
#include <HTTPClient.h>
#include <Adafruit_Fingerprint.h>
#include <HardwareSerial.h>
#include <ArduinoJson.h>

/*
  ========================================================================
  التوصيلات السلكية الصحيحة:
  - VCC  -> 5V أو Vin في الـ ESP32 (لتأمين تيار كافٍ للمستشعر)
  - GND  -> GND
  - TXD  -> GPIO 16 (RX2) بالـ ESP32
  - RXD  -> GPIO 17 (TX2) بالـ ESP32
  ========================================================================
*/

// إعدادات نقطة بث الواي فاي (Access Point)
const char* ap_ssid = "ESP32_Attendance_System"; 
const char* ap_password = "Password1234"; // يجب أن لا تقل عن 8 رموز

// إعدادات خادم البايثون
const char* server_ip = "192.168.4.2"; 
const int server_port = 5000;

// إعداد السيريال الخاص بمستشعر البصمة (سيريال 2)
#define FP_RX 16
#define FP_TX 17
HardwareSerial mySerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);

bool sensorFound = false;
unsigned long lastSensorRetry = 0;

// توقيت فحص طلبات التسجيل اللاسلكية عبر الواي فاي
unsigned long lastEnrollCheck = 0;
const unsigned long enrollCheckInterval = 2000; // فحص كل ثانيتين

void setup() {
  // 1. تهيئة سيريال مراقبة الكمبيوتر (المسار السلكي الأساسي)
  Serial.begin(115200);
  delay(1000); 
  Serial.println("\n====================================");
  Serial.println("[ESP32] Hybrid System Started (Wired + WiFi)");
  Serial.println("====================================");

  // 2. تهيئة سيريال الحساس صراحة مع تحديد الأطراف والسرعة لضمان الاستجابة
  mySerial.begin(57600, SERIAL_8N1, FP_RX, FP_TX);
  delay(100);
  
  finger.begin(57600);
  if (finger.verifyPassword()) {
    Serial.println("[ESP32] SUCCESS: Found DY50 fingerprint sensor!");
    sensorFound = true;
  } else {
    Serial.println("[ESP32] WARNING: Did not find DY50 sensor! Will retry in background...");
    sensorFound = false;
  }

  // 3. تشغيل نقطة بث الواي فاي في الخلفية
  startWiFiAccessPoint();

  Serial.println("\n[System Ready]");
  Serial.println("- For Wired: Use Serial Monitor (115200 baud, Newline) and type 'ENROLL:ID'");
  Serial.println("- For WiFi: Connect your PC to the ESP32 network and run your Python server.\n");
}

void loop() {
  // المسار 1: التحقق من وجود أوامر تسجيل سلكية (عبر الـ Serial Monitor)
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.startsWith("ENROLL:")) {
      int enroll_id = command.substring(7).toInt();
      if (enroll_id > 0 && enroll_id <= 127) {
        runEnrollmentMode(enroll_id);
      } else {
        Serial.println("[Wired Error] ID must be between 1 and 127");
      }
    }
  }

  // المسار 2: التحقق دورياً عبر الواي فاي (فقط إذا كان هناك جهاز كمبيوتر متصل بالشبكة)
  if (WiFi.softAPgetStationNum() > 0 && (millis() - lastEnrollCheck > enrollCheckInterval)) {
    lastEnrollCheck = millis();
    int pending_id = checkPendingEnrollmentFromServer();
    if (pending_id > 0) {
      runEnrollmentMode(pending_id); // تفعيل وضع التسجيل إذا طلب السيرفر ذلك
    }
  }

  // المسار 3: فحص المستشعر إذا وضع مستخدم إصبعه (الحضور والتحقق)
  if (sensorFound) {
    checkFingerprintForAttendance();
  } else {
    // محاولة إعادة الاتصال بالحساس تلقائياً كل 5 ثوانٍ في حال وجود مشكلة في الأسلاك
    if (millis() - lastSensorRetry > 5000) {
      lastSensorRetry = millis();
      if (finger.verifyPassword()) {
        Serial.println("[ESP32] DY50 fingerprint sensor reconnected successfully!");
        sensorFound = true;
      }
    }
  }

  delay(50); // استراحة خفيفة للمعالج لتوفير الطاقة
}

// --- دالة تشغيل نقطة بث الواي فاي ---
void startWiFiAccessPoint() {
  Serial.println("[WiFi] Starting Access Point...");
  WiFi.softAP(ap_ssid, ap_password);
  
  IPAddress IP = WiFi.softAPIP();
  Serial.print("[WiFi] AP IP Address: "); Serial.println(IP);
  Serial.print("[WiFi] SSID: "); Serial.println(ap_ssid);
  Serial.println("[WiFi] AP Started successfully.");
}

// --- دالة فحص البصمة وتسجيل الحضور ---
void checkFingerprintForAttendance() {
  uint8_t p = finger.getImage();
  if (p != FINGERPRINT_OK) return; 

  p = finger.image2Tz();
  if (p != FINGERPRINT_OK) return; 

  p = finger.fingerSearch();
  if (p == FINGERPRINT_OK) {
    int matched_id = finger.fingerID;
    
    // 1. إرسال سلكي متوافق تماماً مع ملف serial_reader.py
    Serial.print("SCAN:");
    Serial.println(matched_id);

    // 2. إرسال لاسلكي (إذا كان السيرفر متصلاً بالواي فاي)
    if (WiFi.softAPgetStationNum() > 0) {
      sendAttendanceToServer(matched_id);
    }
    
    // منع تكرار القراءة حتى يرفع يده
    while (finger.getImage() != FINGERPRINT_NOFINGER) { delay(100); }
  } else if (p == FINGERPRINT_NOTFOUND) {
    // البصمة غير مسجلة (متوافق مع صيغة البايثون)
    Serial.println("NO_MATCH");
    while (finger.getImage() != FINGERPRINT_NOFINGER) { delay(100); }
  }
}

// --- إرسال الحضور إلى خادم البايثون عبر الواي فاي ---
void sendAttendanceToServer(int fingerprint_id) {
  HTTPClient http;
  String url = "http://" + String(server_ip) + ":" + String(server_port) + "/api/attendance";
  
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  
  StaticJsonDocument<200> doc;
  doc["fingerprint_id"] = fingerprint_id;
  String requestBody;
  serializeJson(doc, requestBody);
  
  int httpResponseCode = http.POST(requestBody);
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.print("[HTTP POST] Success. Server Response: ");
    Serial.println(response);
  } else {
    Serial.print("[HTTP POST] Failed to send. Error code: ");
    Serial.println(httpResponseCode);
  }
  http.end();
}

// --- فحص ما إذا كان هناك تسجيل معلق من خادم البايثون ---
int checkPendingEnrollmentFromServer() {
  HTTPClient http;
  String url = "http://" + String(server_ip) + ":" + String(server_port) + "/api/check_enroll";
  
  http.begin(url);
  int httpResponseCode = http.GET();
  int enroll_id = 0;
  
  if (httpResponseCode == 200) {
    String response = http.getString();
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, response);
    if (!error) {
      enroll_id = doc["enroll_id"];
    }
  }
  http.end();
  return enroll_id;
}

// --- دالة تسجيل البصمة ---
void runEnrollmentMode(int id) {
  Serial.println("------------------------------------");
  Serial.print("[Enroll] Entering enrollment mode for ID: ");  Serial.println(id);
  
  int result = -1;
  String error_msg = "";
  
  // خطوة 1: وضع الإصبع للمرة الأولى
  Serial.println("ENROLL_STATUS:Place finger on sensor");
  unsigned long start_time = millis();
  while (true) {
    if (millis() - start_time > 15000) { 
      error_msg = "Timeout waiting for finger (Image 1)";
      break;
    }
    int p = finger.getImage();
    if (p == FINGERPRINT_OK) {
      p = finger.image2Tz(1);
      if (p == FINGERPRINT_OK) { result = 1; break; }
      else { error_msg = "Failed to convert image 1"; break; }
    }
    delay(100);
  }
  
  if (result != 1) { reportEnrollmentResult(id, "failed", error_msg); return; }
  
  // خطوة 2: اطلب رفع الإصبع
  Serial.println("ENROLL_STATUS:Remove finger");
  delay(1000);
  while (finger.getImage() != FINGERPRINT_NOFINGER) { delay(100); }
  
  // خطوة 3: التقاط البصمة للمرة الثانية للمطابقة
  Serial.println("ENROLL_STATUS:Place same finger again");
  result = -1;
  start_time = millis();
  while (true) {
    if (millis() - start_time > 15000) {
      error_msg = "Timeout waiting for finger (Image 2)";
      break;
    }
    int p = finger.getImage();
    if (p == FINGERPRINT_OK) {
      p = finger.image2Tz(2);
      if (p == FINGERPRINT_OK) { result = 2; break; }
      else { error_msg = "Failed to convert image 2"; break; }
    }
    delay(100);
  }
  
  if (result != 2) { reportEnrollmentResult(id, "failed", error_msg); return; }
  
  // خطوة 4 و 5: دمج البصمتين والتخزين بالذاكرة
  int p = finger.createModel();
  if (p == FINGERPRINT_OK) {
    p = finger.storeModel(id);
    if (p == FINGERPRINT_OK) {
      reportEnrollmentResult(id, "success", "");
    } else {
      reportEnrollmentResult(id, "failed", "Failed to store model in sensor memory");
    }
  } else {
    reportEnrollmentResult(id, "failed", "Fingerprints did not match. Try again");
  }
  Serial.println("------------------------------------");
}

// --- دالة تقرير نتيجة التبصيم (متوافقة تماماً مع صيغة استقراء السيريال في البايثون) ---
void reportEnrollmentResult(int id, String status, String error_message) {
  // 1. التقرير عبر السلك (متوافق مع ملف serial_reader.py)
  if (status == "success") {
    Serial.print("ENROLL_OK:"); 
    Serial.println(id);
  } else {
    Serial.print("ENROLL_FAIL:"); 
    Serial.print(id); 
    Serial.print(":"); 
    Serial.println(error_message);
  }

  // 2. التقرير اللاسلكي (HTTP POST إلى سيرفر البايثون)
  if (WiFi.softAPgetStationNum() > 0) {
    HTTPClient http;
    String url = "http://" + String(server_ip) + ":" + String(server_port) + "/api/enroll_result";
    
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    
    StaticJsonDocument<300> doc;
    doc["status"] = status;
    doc["fingerprint_id"] = id;
    if (error_message != "") { doc["message"] = error_message; }
    
    String requestBody;
    serializeJson(doc, requestBody);
    
    int httpResponseCode = http.POST(requestBody);
    http.end();
  }
}