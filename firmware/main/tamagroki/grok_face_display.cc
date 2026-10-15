#include "grok_face_display.h"
#include "tamagroki.h"
#include "application.h"
#include "device_state.h"

#include <esp_log.h>
#include <string.h>

#define TAG "GrokFace"

#ifndef CONFIG_TAMAGROKI_BG_COLOR
#define CONFIG_TAMAGROKI_BG_COLOR 0x9B7FE0
#endif
#ifndef CONFIG_TAMAGROKI_EYE_TILT_DEG
#define CONFIG_TAMAGROKI_EYE_TILT_DEG 12
#endif

GrokFaceDisplay::~GrokFaceDisplay() {
    if (timer_) lv_timer_delete(timer_);
}

void GrokFaceDisplay::SetupUI() {
    // Let the stock UI build its objects (other code paths touch them),
    // then cover everything with the face on the top layer.
    SpiLcdDisplay::SetupUI();
    DisplayLockGuard lock(this);
    FaceConfig cfg;
    cfg.bg_color = CONFIG_TAMAGROKI_BG_COLOR;
    cfg.tilt_deg = (float)CONFIG_TAMAGROKI_EYE_TILT_DEG;
    int scale_w = width_;
    cfg.eye_spacing = cfg.eye_spacing * scale_w / 480;
    cfg.eye_length = cfg.eye_length * scale_w / 480;
    cfg.eye_width = cfg.eye_width * scale_w / 480;
    face_.Create(lv_layer_top(), width_, height_, cfg);
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_hex(CONFIG_TAMAGROKI_BG_COLOR), 0);
    timer_ = lv_timer_create(TimerCb, 33, this);
    ESP_LOGI(TAG, "Tamagroki face ready (bg #%06X, tilt %d)", (unsigned)CONFIG_TAMAGROKI_BG_COLOR,
             CONFIG_TAMAGROKI_EYE_TILT_DEG);
}

void GrokFaceDisplay::TimerCb(lv_timer_t* t) {
    static_cast<GrokFaceDisplay*>(lv_timer_get_user_data(t))->OnTick();
}

void GrokFaceDisplay::OnTick() {
    // Runs inside the LVGL task with the LVGL lock held.
    uint32_t now = lv_tick_get();
    int ds = (int)Application::GetInstance().GetDeviceState();
    if (ds != last_device_state_) {
        thinking_hint_ = false;
        last_device_state_ = ds;
    }
    FaceState fs;
    switch ((DeviceState)ds) {
        case kDeviceStateListening: fs = thinking_hint_ ? FaceState::kThinking : FaceState::kListening; break;
        case kDeviceStateSpeaking: fs = FaceState::kSpeaking; break;
        case kDeviceStateConnecting:
        case kDeviceStateStarting:
        case kDeviceStateActivating:
        case kDeviceStateUpgrading: fs = FaceState::kBusy; break;
        // Idle = no conversation open (wake word armed, not streaming the mic):
        // always show the sleeping face, so awake eyes reliably mean "listening".
        // The channel-closed path (relay close, idle close, network drop, BOOT stop)
        // always lands in idle, so this does not depend on the relay.
        case kDeviceStateIdle: fs = FaceState::kSleep; break;
        default: fs = power_save_ ? FaceState::kSleep : FaceState::kIdle; break;
    }
    face_.SetState(fs, now);
    float lvl = tamagroki::g_playback_level.load(std::memory_order_relaxed);
    face_.SetAudioLevel(lvl);
    // decay so the bounce settles when playback pauses (the audio task refreshes it per frame)
    tamagroki::g_playback_level.store(lvl * 0.8f, std::memory_order_relaxed);
    if (notification_until_ && (int32_t)(now - notification_until_) > 0) {
        notification_until_ = 0;
        face_.SetCaption(system_caption_.c_str());
    }
    face_.Tick(now);
}

void GrokFaceDisplay::SetEmotion(const char* emotion) {
    if (emotion == nullptr) return;
    DisplayLockGuard lock(this);
    // The relay sends {"type":"llm","emotion":"thinking"} while the model works.
    if (strcmp(emotion, "thinking") == 0) thinking_hint_ = true;
    else if (strcmp(emotion, "neutral") == 0 || strcmp(emotion, "listening") == 0) thinking_hint_ = false;
    else if (strcmp(emotion, "sleepy") == 0) power_save_ = true;
}

void GrokFaceDisplay::SetChatMessage(const char* role, const char* content) {
    if (role == nullptr) return;
    DisplayLockGuard lock(this);
    if (strcmp(role, "system") == 0) {
        // Wi-Fi provisioning instructions, activation codes, errors: always show.
        system_caption_ = content ? content : "";
        if (!notification_until_) face_.SetCaption(system_caption_.c_str());
        return;
    }
#if CONFIG_TAMAGROKI_SHOW_SUBTITLES
    face_.SetCaption(content ? content : "");
#endif
}

void GrokFaceDisplay::ClearChatMessages() {
    DisplayLockGuard lock(this);
    system_caption_.clear();
    face_.SetCaption("");
}

void GrokFaceDisplay::SetStatus(const char* status) {
    // Status text (standby/listening/...) is expressed by the eyes instead.
    (void)status;
}

void GrokFaceDisplay::ShowNotification(const char* notification, int duration_ms) {
    if (notification == nullptr) return;
    DisplayLockGuard lock(this);
    face_.SetCaption(notification);
    notification_until_ = lv_tick_get() + (uint32_t)duration_ms;
    if (notification_until_ == 0) notification_until_ = 1;
}

void GrokFaceDisplay::ShowNotification(const std::string& notification, int duration_ms) {
    ShowNotification(notification.c_str(), duration_ms);
}

void GrokFaceDisplay::SetPowerSaveMode(bool on) {
    DisplayLockGuard lock(this);
    power_save_ = on;
}

void GrokFaceDisplay::Nudge() {
    DisplayLockGuard lock(this);
    power_save_ = false;
}
