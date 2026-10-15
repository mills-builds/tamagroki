// Minimal QMI8658 accelerometer poller: fires a callback when the cube is picked up
// (sustained deviation of |a| from 1 g, or a big orientation change).
#pragma once
#include "i2c_device.h"
#include <functional>

class Qmi8658Pickup : public I2cDevice {
public:
    Qmi8658Pickup(i2c_master_bus_handle_t bus, uint8_t addr = 0x6B);
    bool ok() const { return ok_; }
    void Start(std::function<void()> on_pickup, int threshold_mg);

private:
    static void TaskEntry(void* arg);
    void Run();
    bool ReadAccelMg(float& x, float& y, float& z);
    bool ok_ = false;
    int threshold_mg_ = 350;
    std::function<void()> on_pickup_;
};
