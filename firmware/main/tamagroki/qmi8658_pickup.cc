#include "qmi8658_pickup.h"
#include <esp_log.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <math.h>

#define TAG "Qmi8658Pickup"

// Registers (QMI8658 datasheet rev 0.9)
static constexpr uint8_t REG_WHO_AM_I = 0x00;  // 0x05
static constexpr uint8_t REG_CTRL1 = 0x02;     // bit6 ADDR_AI auto increment
static constexpr uint8_t REG_CTRL2 = 0x03;     // accel FS[6:4], ODR[3:0]
static constexpr uint8_t REG_CTRL7 = 0x08;     // bit0 aEN
static constexpr uint8_t REG_AX_L = 0x35;

Qmi8658Pickup::Qmi8658Pickup(i2c_master_bus_handle_t bus, uint8_t addr) : I2cDevice(bus, addr) {
    uint8_t who = ReadReg(REG_WHO_AM_I);
    if (who != 0x05) {
        ESP_LOGW(TAG, "QMI8658 not found (WHO_AM_I=0x%02X)", who);
        return;
    }
    WriteReg(REG_CTRL1, 0x40);  // address auto-increment, little endian
    WriteReg(REG_CTRL2, 0x16);  // +-4 g (FS=001), ODR ~ 62.5 Hz (0110)
    WriteReg(REG_CTRL7, 0x01);  // accel only
    ok_ = true;
    ESP_LOGI(TAG, "QMI8658 ready");
}

bool Qmi8658Pickup::ReadAccelMg(float& x, float& y, float& z) {
    uint8_t b[6];
    ReadRegs(REG_AX_L, b, 6);
    auto s = [&](int i) { return (int16_t)(b[i] | (b[i + 1] << 8)); };
    const float lsb_per_g = 8192.0f;  // +-4 g
    x = s(0) * 1000.0f / lsb_per_g;
    y = s(2) * 1000.0f / lsb_per_g;
    z = s(4) * 1000.0f / lsb_per_g;
    return true;
}

void Qmi8658Pickup::Start(std::function<void()> on_pickup, int threshold_mg) {
    if (!ok_) return;
    on_pickup_ = std::move(on_pickup);
    threshold_mg_ = threshold_mg;
    xTaskCreate(TaskEntry, "imu_pickup", 3072, this, 2, nullptr);
}

void Qmi8658Pickup::TaskEntry(void* arg) { static_cast<Qmi8658Pickup*>(arg)->Run(); }

void Qmi8658Pickup::Run() {
    float rx = 0, ry = 0, rz = 0;  // slow "resting" gravity estimate
    bool init = false;
    int hits = 0;
    TickType_t cooldown_until = 0;
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(50));
        float x, y, z;
        if (!ReadAccelMg(x, y, z)) continue;
        if (!init) { rx = x; ry = y; rz = z; init = true; continue; }
        float dx = x - rx, dy = y - ry, dz = z - rz;
        float dev = sqrtf(dx * dx + dy * dy + dz * dz);
        // resting estimate follows slowly (~2 s time constant)
        rx += 0.025f * dx; ry += 0.025f * dy; rz += 0.025f * dz;
        hits = dev > threshold_mg_ ? hits + 1 : 0;
        if (hits >= 3 && xTaskGetTickCount() > cooldown_until) {  // ~150 ms of motion
            hits = 0;
            cooldown_until = xTaskGetTickCount() + pdMS_TO_TICKS(8000);
            ESP_LOGI(TAG, "pick-up detected (dev=%.0f mg)", dev);
            if (on_pickup_) on_pickup_();
        }
    }
}
