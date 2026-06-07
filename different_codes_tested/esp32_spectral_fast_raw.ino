/*
  ESP32 Spectral Sensor - Fast Raw Channel Output
  Streams all 18 channels at maximum speed
*/

#include "SparkFun_AS7265X.h"

AS7265X sensor;
unsigned long sample_count = 0;

void setup() {
    Serial.begin(115200);
    delay(500);
    
    Serial.println("\n🚀 FAST RAW CHANNEL OUTPUT\n");

    if (sensor.begin() == false) {
        Serial.println("❌ SENSOR NOT FOUND");
        while (1);
    }
    
    Serial.println("✅ Sensor initialized");
    
    // Enable all 3 LED lights
    sensor.setBulbCurrent(10, 0);
    sensor.setBulbCurrent(10, 1);
    sensor.setBulbCurrent(10, 2);
    sensor.enableBulb(0);
    sensor.enableBulb(1);
    sensor.enableBulb(2);
    Serial.println("✅ LEDs ON\n");
    
    Serial.println("410nm | 435nm | 460nm | 485nm | 510nm | 535nm | 560nm | 585nm | 610nm | 645nm | 680nm | 705nm | 730nm | 760nm | 810nm | 860nm | 900nm | 940nm");
}

void loop() {
    sensor.takeMeasurements();
    
    // Print all 18 channels with minimal formatting
    Serial.printf("%5.0f | ", sensor.getCalibratedA());
    Serial.printf("%5.0f | ", sensor.getCalibratedB());
    Serial.printf("%5.0f | ", sensor.getCalibratedC());
    Serial.printf("%5.0f | ", sensor.getCalibratedD());
    Serial.printf("%5.0f | ", sensor.getCalibratedE());
    Serial.printf("%5.0f | ", sensor.getCalibratedF());
    Serial.printf("%5.0f | ", sensor.getCalibratedG());
    Serial.printf("%5.0f | ", sensor.getCalibratedH());
    Serial.printf("%5.0f | ", sensor.getCalibratedR());
    Serial.printf("%5.0f | ", sensor.getCalibratedI());
    Serial.printf("%5.0f | ", sensor.getCalibratedS());
    Serial.printf("%5.0f | ", sensor.getCalibratedJ());
    Serial.printf("%5.0f | ", sensor.getCalibratedT());
    Serial.printf("%5.0f | ", sensor.getCalibratedU());
    Serial.printf("%5.0f | ", sensor.getCalibratedV());
    Serial.printf("%5.0f | ", sensor.getCalibratedW());
    Serial.printf("%5.0f | ", sensor.getCalibratedK());
    Serial.printf("%5.0f\n", sensor.getCalibratedL());
    
    sample_count++;
    // No delay - maximum speed
}
