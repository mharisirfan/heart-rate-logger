/*
  ESP32 Spectral Sensor - Heart Rate Detection on Wrist
  Real-time PPG analysis with automatic BPM calculation
  
  Hardware:
  - ESP32 WROOM-32E
  - AS7265X Spectral Triad sensor over I2C
*/

#include "SparkFun_AS7265X.h"

AS7265X sensor;

unsigned long sample_count = 0;

// PPG Signal storage (last 100 samples = 5 seconds at 20Hz)
const int BUFFER_SIZE = 100;
float ppg_680[BUFFER_SIZE];  // Red
int buffer_ptr = 0;
int peak_indices[20];  // Store peak positions
int peak_count = 0;

// Beat detection
bool last_was_trough = true;  // Start looking for peak
float threshold_value = 0;
unsigned long last_beat_time = 0;

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n\n╔════════════════════════════════════════════╗");
    Serial.println("║  PPG Heart Rate Monitor (Wrist Mode)       ║");
    Serial.println("╚════════════════════════════════════════════╝\n");

    // Initialize sensor
    if (sensor.begin() == false) {
        Serial.println("❌ SENSOR NOT FOUND");
        while (1);
    }
    
    Serial.println("✅ Sensor initialized\n");
    
    // Enable all 3 LED lights
    Serial.println("🔦 Turning on all LED lights...");
    sensor.setBulbCurrent(10, 0);  // White LED
    sensor.setBulbCurrent(10, 1);  // Red LED
    sensor.setBulbCurrent(10, 2);  // NIR LED
    sensor.enableBulb(0);
    sensor.enableBulb(1);
    sensor.enableBulb(2);
    Serial.println("✅ LEDs ON\n");
    
    Serial.println("📊 REAL-TIME PPG OUTPUT:");
    Serial.println("Sample# | 680nm(R) | 730nm(N) | 860nm(N) | 🫀 HR(BPM) | Confidence");
    Serial.println("════════════════════════════════════════════════════════════════════\n");
}

int detectPeaksAdvanced(float* buffer, int buf_size, int* out_peaks, int max_peaks) {
    if (buf_size < 5) return 0;
    
    // Step 1: Calculate DC (mean) and extract AC component
    float sum = 0;
    float min_val = 99999, max_val = 0;
    for (int i = 0; i < buf_size; i++) {
        sum += buffer[i];
        if (buffer[i] < min_val) min_val = buffer[i];
        if (buffer[i] > max_val) max_val = buffer[i];
    }
    float dc = sum / buf_size;
    float ac_amplitude = (max_val - min_val) / 2.0;
    
    if (ac_amplitude < 1) return 0;  // Very lenient threshold
    
    // Step 2: Normalize AC signal (remove DC, scale -1 to +1)
    float ac_signal[buf_size];
    for (int i = 0; i < buf_size; i++) {
        ac_signal[i] = (buffer[i] - dc) / (ac_amplitude + 0.1);  // Avoid division by zero
    }
    
    // Step 3: Detect peaks in normalized signal (very low threshold = 0.0)
    int peaks_found = 0;
    float threshold = 0.0;  // Find ANY local maximum
    
    for (int i = 2; i < buf_size - 2; i++) {
        // Look for local maximum
        if (ac_signal[i] > ac_signal[i-1] && 
            ac_signal[i] > ac_signal[i+1] &&
            ac_signal[i] > ac_signal[i-2] &&
            ac_signal[i] > ac_signal[i+2]) {
            out_peaks[peaks_found++] = i;
            if (peaks_found >= max_peaks) break;
        }
    }
    
    return peaks_found;
}

int calculateHeartRate(float* buffer, int buf_size) {
    int peaks[20];
    int num_peaks = detectPeaksAdvanced(buffer, buf_size, peaks, 20);
    
    if (num_peaks < 2) return 0;
    
    // Calculate average interval between peaks
    float total_interval = 0;
    for (int i = 1; i < num_peaks; i++) {
        total_interval += (peaks[i] - peaks[i-1]);
    }
    float avg_interval = total_interval / (num_peaks - 1);
    
    // Convert interval (samples) to BPM
    // 20 Hz = 50ms per sample
    // Heart rate = 60 / (interval in seconds)
    float interval_seconds = avg_interval * 0.05;
    float bpm = 60.0 / interval_seconds;
    
    // Valid range
    if (bpm < 40 || bpm > 180) return 0;
    return (int)round(bpm);
}

// Check if current sample is a heartbeat (like sawStartOfBeat())
bool sawHeartBeat(float current_value, float buffer_mean) {
    // Find peak: current value is higher than mean AND higher than last value
    if (current_value > buffer_mean && last_was_trough) {
        // We just transitioned from trough to peak - HEARTBEAT!
        last_was_trough = false;
        last_beat_time = millis();
        return true;
    }
    
    // Check if we're back at trough
    if (current_value < buffer_mean) {
        last_was_trough = true;
    }
    
    return false;
}

void loop() {
    sensor.takeMeasurements();
    
    // Get RED channel (680nm)
    float val_680 = sensor.getCalibratedS();
    
    // Store in circular buffer
    ppg_680[buffer_ptr] = val_680;
    buffer_ptr = (buffer_ptr + 1) % BUFFER_SIZE;
    
    sample_count++;
    
    // Quick beat detection every sample (no heavy processing)
    if (sample_count > BUFFER_SIZE) {
        // Rapid mean calculation (single pass)
        float sum = 0;
        for (int i = 0; i < BUFFER_SIZE; i++) sum += ppg_680[i];
        float mean = sum / BUFFER_SIZE;
        
        // Instant beat detection
        if (sawHeartBeat(val_680, mean)) {
            Serial.print("♥");  // Super fast - just print heart
        }
    }
    
    // BPM calculation every 20 samples only (less frequent)
    if (sample_count % 20 == 0 && sample_count > BUFFER_SIZE) {
        int hr = calculateHeartRate(ppg_680, BUFFER_SIZE);
        if (hr > 0) {
            Serial.printf(" [%d BPM]\n", hr);
        } else {
            Serial.print(" [---]\n");
        }
    }
    
    delay(50);  // 20 Hz sampling
}
