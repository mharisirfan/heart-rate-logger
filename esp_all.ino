/*
  ESP32 Spectral Sensor BLE Server
  Sends:
  sample,millis,D,F,R

  Fast test version:
  - selected 3 channels only
  - integration cycles = 2
  - gain = 64x
  - white bulb enabled during measurement
*/

#include "SparkFun_AS7265X.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

AS7265X sensor;

#define SERVICE_UUID        "12345678-1234-1234-1234-123456789012"
#define SPECTRAL_CHAR_UUID  "87654321-4321-4321-4321-210987654321"

BLECharacteristic *pSpectralChar;
BLEServer *pServer = NULL;

bool deviceConnected = false;
unsigned long sampleCounter = 0;

unsigned long lastFsPrint = 0;
unsigned long samplesThisSecond = 0;

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *pServer) {
    deviceConnected = true;
    Serial.println("BLE Client connected");
  }

  void onDisconnect(BLEServer *pServer) {
    deviceConnected = false;
    Serial.println("BLE Client disconnected");
    delay(500);
    BLEDevice::getAdvertising()->start();
    Serial.println("Advertising restarted...");
  }
};

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\nESP32 Spectral Sensor BLE Server");
  Serial.println("Sending sample,millis,D,F,R");

  if (!sensor.begin()) {
    Serial.println("Sensor not detected. Check wiring!");
    while (1);
  }

  sensor.disableIndicator();

  sensor.setIntegrationCycles(2);
  sensor.setGain(64);
  sensor.setBulbCurrent(50, 0);

  sensor.disableBulb(0);
  sensor.disableBulb(1);
  sensor.disableBulb(2);

  BLEDevice::init("ESP32-Spectral");

  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);

  pSpectralChar = pService->createCharacteristic(
    SPECTRAL_CHAR_UUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
  );

  pSpectralChar->addDescriptor(new BLE2902());
  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  BLEDevice::startAdvertising();

  Serial.println("Sensor initialized");
  Serial.println("BLE advertising started\n");
  Serial.println("sample,millis,D,F,R");

  lastFsPrint = millis();
}

void loop() {
  // sensor.enableBulb(0);
  // sensor.disableBulb(1);
  // sensor.disableBulb(2);

  sensor.takeMeasurementsWithBulb();

 float R = sensor.getCalibratedR();

char buffer[80];

snprintf(buffer, sizeof(buffer),
         "%lu,%lu,%.5f",
         sampleCounter,
         millis(),
         R);

  Serial.println(buffer);

  if (deviceConnected) {
    pSpectralChar->setValue((uint8_t*)buffer, strlen(buffer));
    pSpectralChar->notify();
  }

  sampleCounter++;
  samplesThisSecond++;

  if (millis() - lastFsPrint >= 1000) {
    Serial.print("Actual fs = ");
    Serial.print(samplesThisSecond);
    Serial.println(" Hz");

    samplesThisSecond = 0;
    lastFsPrint = millis();
  }
}