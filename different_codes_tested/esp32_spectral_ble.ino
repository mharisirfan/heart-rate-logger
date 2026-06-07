/*
  ESP32 Spectral Sensor BLE Server
  Reads 18 spectral channels from AS7265X sensor and broadcasts via BLE.
  
  Hardware:
  - ESP32 WROOM DA
  - AS7265X Spectral Triad sensor over I2C
  
  Installation:
  1. Install SparkFun AS7265X library in Arduino IDE
  2. Select "ESP32 Dev Module" board
  3. Upload this code
*/

#include "SparkFun_AS7265X.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

AS7265X sensor;

// BLE UUIDs (you can generate unique ones at uuidgenerator.net)
#define SERVICE_UUID           "12345678-1234-1234-1234-123456789012"
#define SPECTRAL_CHAR_UUID     "87654321-4321-4321-4321-210987654321"

BLECharacteristic *pSpectralChar;
BLEServer *pServer = NULL;
bool deviceConnected = false;

class MyServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer *pServer) {
        deviceConnected = true;
        Serial.println("BLE Client connected");
    };

    void onDisconnect(BLEServer *pServer) {
        deviceConnected = false;
        Serial.println("BLE Client disconnected");
        delay(500);
        // Re-start advertising after disconnect so client can reconnect
        BLEDevice::getAdvertising()->start();
        Serial.println("Advertising restarted, waiting for reconnection...");
    }
};

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n\nESP32 Spectral Sensor BLE Server (Fast Mode)");
    Serial.println("===========================================");

    // Initialize sensor
    if (sensor.begin() == false) {
        Serial.println("Sensor does not appear to be connected. Please check wiring. Freezing...");
        while (1);
    }
    
    Serial.println("Sensor initialized successfully");
    
    // Enable all 3 LED lights (White, Red, NIR)
    sensor.setBulbCurrent(10, 0);  // Device 0: White LED, 10mA
    sensor.setBulbCurrent(10, 1);  // Device 1: Red LED, 10mA
    sensor.setBulbCurrent(10, 2);  // Device 2: NIR LED, 10mA
    sensor.enableBulb(0);
    sensor.enableBulb(1);
    sensor.enableBulb(2);
    Serial.println("✅ All 3 LED lights enabled");

    // Initialize BLE
    BLEDevice::init("ESP32-Spectral");
    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());

    // Create BLE Service
    BLEService *pService = pServer->createService(SERVICE_UUID);

    // Create BLE Characteristic for spectral data
    pSpectralChar = pService->createCharacteristic(
        SPECTRAL_CHAR_UUID,
        BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
    );

    // Add descriptor for notifications
    pSpectralChar->addDescriptor(new BLE2902());

    // Start service and advertising
    pService->start();
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(false);
    pAdvertising->setMinPreferred(0x0);
    BLEDevice::startAdvertising();
    
    Serial.println("BLE advertising started");
    Serial.println("Looking for BLE clients...\n");
}

void loop() {
    // Take measurements from sensor
    sensor.takeMeasurements();

    // Send 3 wavelengths for robust HR calculation: 680nm (red), 870nm (IR), 730nm (near-IR)
    float s680 = sensor.getCalibratedS();     // 680nm - red
    float s870 = sensor.getCalibratedR();     // 870nm - IR
    float s730 = sensor.getCalibratedT();     // 730nm - near-IR

    // Format as comma-separated values with 5 decimal places
    char buffer[60];
    snprintf(buffer, sizeof(buffer), "%.5f,%.5f,%.5f", s680, s870, s730);

    // Print to Serial for debugging
    Serial.println(buffer);

    // Send to BLE if a client is connected
    if (deviceConnected) {
        pSpectralChar->setValue(buffer);
        pSpectralChar->notify();
    }

    delay(50); // 20 Hz sampling rate (50ms per sample)
}
