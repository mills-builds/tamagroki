// SpiLcdDisplay that replaces xiaozhi's chat UI with the full-screen Tamagroki face.
#pragma once
#include "lcd_display.h"
#include "grok_face.h"
#include <string>

class GrokFaceDisplay : public SpiLcdDisplay {
public:
    using SpiLcdDisplay::SpiLcdDisplay;
    ~GrokFaceDisplay() override;

    void SetupUI() override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    void ClearChatMessages() override;
    void SetStatus(const char* status) override;
    void ShowNotification(const char* notification, int duration_ms = 3000) override;
    void ShowNotification(const std::string& notification, int duration_ms = 3000) override;
    void SetPowerSaveMode(bool on) override;
    void UpdateStatusBar(bool update_all = false) override {}

    // Simulates a "pick-up" or other external nudge: wakes the face from sleep.
    void Nudge();

private:
    static void TimerCb(lv_timer_t* t);
    void OnTick();

    GrokFace face_;
    lv_timer_t* timer_ = nullptr;
    bool power_save_ = false;
    bool thinking_hint_ = false;   // set by llm emotion "thinking", cleared on state change
    int last_device_state_ = -1;
    uint32_t notification_until_ = 0;
    std::string system_caption_;
};
