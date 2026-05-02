#pragma once

// ============================================================================
// Re-Tech Fusion — ESP32 Node Configuration
// All pins, intervals, thresholds live here. No magic numbers in source files.
// ============================================================================

// ---- Identity --------------------------------------------------------------
#define FW_VERSION       "1.0.0"
#define DEVICE_ID        "esp32_node_01"
#define SITE_ID          "insat_lab_zone_a"

// ---- Serial ----------------------------------------------------------------
#define SERIAL_BAUD      115200

// ---- I2C / BME280 ----------------------------------------------------------
#define I2C_SDA_PIN      21
#define I2C_SCL_PIN      22
#define BME280_I2C_ADDR  0x76

// ---- DS18B20 ---------------------------------------------------------------
#define DS18B20_PIN      4
#define DS18B20_RESOLUTION_BITS 12

// ---- Timing (ms) -----------------------------------------------------------
#define HEARTBEAT_INTERVAL_MS    1000UL
#define SENSOR_READ_INTERVAL_MS  1000UL
#define PUBLISH_INTERVAL_MS      10000UL

// ---- Reconnect backoff (ms) ------------------------------------------------
#define RECONNECT_BACKOFF_MIN_MS 1000UL
#define RECONNECT_BACKOFF_MAX_MS 60000UL

// ---- Wi-Fi -----------------------------------------------------------------
#define WIFI_HOSTNAME           DEVICE_ID
#define WIFI_CONNECT_TIMEOUT_MS 15000UL
#define WIFI_POLL_INTERVAL_MS     250UL

// ---- NTP -------------------------------------------------------------------
#define NTP_SERVER_PRIMARY    "pool.ntp.org"
#define NTP_SERVER_SECONDARY  "time.nist.gov"
#define NTP_TZ_OFFSET_S       0  // UTC; schema timestamps end with 'Z'

// ---- Buffering -------------------------------------------------------------
#define RING_BUFFER_CAPACITY     100

// ---- Validation ranges -----------------------------------------------------
#define TEMP_MIN_C        -40.0f
#define TEMP_MAX_C         85.0f
#define HUMIDITY_MIN_PCT    0.0f
#define HUMIDITY_MAX_PCT  100.0f
#define PRESSURE_MIN_HPA  300.0f
#define PRESSURE_MAX_HPA 1100.0f

// ---- Cross-sensor drift ----------------------------------------------------
#define DRIFT_ALERT_THRESHOLD_C  2.0f

// ---- MQTT ------------------------------------------------------------------
#define MQTT_TOPIC_READINGS  "retech/devices/" DEVICE_ID "/readings"
#define MQTT_QOS             1
#define MQTT_RETAINED        false
#define MQTT_KEEPALIVE_S     30
// PubSubClient default buffer is 256 B; our payload is ~360 B + topic + headers.
// Bump to 768 to cover headroom plus any growth from future schema extensions.
#define MQTT_TX_BUFFER_SIZE  768
#define MQTT_SOCKET_TIMEOUT_S 5
