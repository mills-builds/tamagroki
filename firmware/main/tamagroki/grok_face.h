// Tamagroki cube face: purple background + two black tilted pill eyes.
// Pure LVGL v9 code (no ESP-IDF deps) so the same file runs in the desktop
// simulator (sim/face) and on the ESP32-S3.
#pragma once
#include <lvgl.h>
#include <stdint.h>

enum class FaceState : uint8_t {
    kIdle = 0,
    kListening,
    kThinking,
    kSpeaking,
    kSleep,
    kBusy,  // connecting / starting / activating (rendered like a slow "thinking")
};

const char* FaceStateName(FaceState s);

struct FaceConfig {
    uint32_t bg_color = 0x9B7FE0;   // solid background (RGB888)
    uint32_t eye_color = 0x000000;  // pill eyes
    float tilt_deg = 12.0f;         // lean of the pills from vertical (+ = top leans right)
    int eye_spacing = 150;          // distance between eye centres (px @480)
    int eye_length = 110;           // distance between the pill's cap centres
    int eye_width = 84;             // pill thickness
    int center_y_offset = -10;      // eyes slightly above centre
};

class GrokFace {
public:
    // Creates the face as a full-size child of `parent` (screen or lv_layer_top()).
    void Create(lv_obj_t* parent, int width, int height, const FaceConfig& cfg);
    void SetState(FaceState s, uint32_t now_ms);
    FaceState state() const { return state_; }
    // 0..1 loudness of the audio currently being played (speaking bounce).
    void SetAudioLevel(float level) { audio_level_target_ = level < 0 ? 0 : (level > 1 ? 1 : level); }
    // Small caption at the bottom (wifi setup, errors, optional subtitles). "" hides it.
    void SetCaption(const char* text);
    void SetBackground(uint32_t rgb);
    // Advance the animation to absolute time now_ms. Call at ~30 Hz.
    void Tick(uint32_t now_ms);
    lv_obj_t* root() const { return root_; }

private:
    struct EyePose {
        float dx, dy;    // offset from rest centre
        float length;    // cap-centre distance
        float width;     // thickness
        float angle;     // degrees from vertical
    };
    void ApplyEye(int idx, const EyePose& p);
    float Rand01();

    FaceConfig cfg_;
    lv_obj_t* root_ = nullptr;
    lv_obj_t* eyes_[2] = {nullptr, nullptr};
    lv_point_precise_t pts_[2][2];
    lv_obj_t* caption_ = nullptr;
    lv_obj_t* zzz_ = nullptr;
    int w_ = 480, h_ = 480;

    FaceState state_ = FaceState::kIdle;
    uint32_t state_since_ = 0;
    uint32_t last_tick_ = 0;
    uint32_t rng_ = 0x1234567u;

    // idle behaviour
    uint32_t next_blink_ = 2500;
    uint32_t blink_start_ = 0;
    bool double_blink_ = false;
    uint32_t next_glance_ = 4000;
    float glance_target_x_ = 0, glance_target_y_ = 0;
    float glance_x_ = 0, glance_y_ = 0;

    // smoothed values
    float audio_level_target_ = 0, audio_level_ = 0;
    float perk_ = 0;   // 0..1 listening perk
    float sleep_ = 0;  // 0..1 eyes closed for sleep
    float think_ = 0;  // 0..1 thinking pose
};
