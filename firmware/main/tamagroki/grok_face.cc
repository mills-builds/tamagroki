#include "grok_face.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static inline float lerp(float a, float b, float t) { return a + (b - a) * t; }
static inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }
// exponential smoothing that is frame-rate independent
static inline float approach(float cur, float target, float rate_per_s, float dt) {
    float k = 1.0f - expf(-rate_per_s * dt);
    return cur + (target - cur) * k;
}

const char* FaceStateName(FaceState s) {
    switch (s) {
        case FaceState::kIdle: return "idle";
        case FaceState::kListening: return "listening";
        case FaceState::kThinking: return "thinking";
        case FaceState::kSpeaking: return "speaking";
        case FaceState::kSleep: return "sleep";
        case FaceState::kBusy: return "busy";
    }
    return "?";
}

float GrokFace::Rand01() {
    rng_ = rng_ * 1664525u + 1013904223u;
    return (rng_ >> 8) / 16777216.0f;
}

void GrokFace::Create(lv_obj_t* parent, int width, int height, const FaceConfig& cfg) {
    cfg_ = cfg;
    w_ = width;
    h_ = height;
    root_ = lv_obj_create(parent);
    lv_obj_remove_style_all(root_);
    lv_obj_set_size(root_, width, height);
    lv_obj_set_pos(root_, 0, 0);
    lv_obj_set_style_bg_opa(root_, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(root_, lv_color_hex(cfg_.bg_color), 0);
    lv_obj_remove_flag(root_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(root_, LV_OBJ_FLAG_CLICKABLE);

    for (int i = 0; i < 2; i++) {
        eyes_[i] = lv_line_create(root_);
        lv_obj_remove_flag(eyes_[i], LV_OBJ_FLAG_CLICKABLE);
        lv_obj_set_style_line_color(eyes_[i], lv_color_hex(cfg_.eye_color), 0);
        lv_obj_set_style_line_rounded(eyes_[i], true, 0);
        lv_obj_set_style_line_width(eyes_[i], cfg_.eye_width, 0);
        lv_obj_set_pos(eyes_[i], 0, 0);
        lv_obj_set_size(eyes_[i], width, height);
    }

    zzz_ = lv_label_create(root_);
    lv_label_set_text(zzz_, "z z z");
    lv_obj_set_style_text_color(zzz_, lv_color_hex(cfg_.eye_color), 0);
    lv_obj_set_style_text_opa(zzz_, LV_OPA_70, 0);
#if LV_FONT_MONTSERRAT_24
    lv_obj_set_style_text_font(zzz_, &lv_font_montserrat_24, 0);
#endif
    lv_obj_add_flag(zzz_, LV_OBJ_FLAG_HIDDEN);

    caption_ = lv_label_create(root_);
    lv_obj_set_width(caption_, width * 70 / 100);
    lv_label_set_long_mode(caption_, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(caption_, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(caption_, lv_color_hex(0x1A1033), 0);
#if LV_FONT_MONTSERRAT_24
    lv_obj_set_style_text_font(caption_, &lv_font_montserrat_24, 0);
#endif
    lv_obj_align(caption_, LV_ALIGN_BOTTOM_MID, 0, -height / 12);
    lv_obj_add_flag(caption_, LV_OBJ_FLAG_HIDDEN);

    Tick(0);
}

void GrokFace::SetBackground(uint32_t rgb) {
    cfg_.bg_color = rgb;
    if (root_) lv_obj_set_style_bg_color(root_, lv_color_hex(rgb), 0);
}

void GrokFace::SetCaption(const char* text) {
    if (!caption_) return;
    if (text == nullptr || text[0] == '\0') {
        lv_obj_add_flag(caption_, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_label_set_text(caption_, text);
        lv_obj_remove_flag(caption_, LV_OBJ_FLAG_HIDDEN);
    }
}

void GrokFace::SetState(FaceState s, uint32_t now_ms) {
    if (s == state_) return;
    state_ = s;
    state_since_ = now_ms;
    if (s == FaceState::kListening) {
        // a quick "oh!" blink when we start listening
        blink_start_ = now_ms;
        double_blink_ = false;
    }
}

void GrokFace::ApplyEye(int idx, const EyePose& p) {
    float base_x = w_ / 2.0f + (idx == 0 ? -1 : 1) * cfg_.eye_spacing / 2.0f;
    float base_y = h_ / 2.0f + cfg_.center_y_offset;
    float cx = base_x + p.dx, cy = base_y + p.dy;
    float a = p.angle * (float)M_PI / 180.0f;
    // direction of the pill's long axis (vertical rotated by angle, top leans right for +)
    float ux = sinf(a), uy = -cosf(a);
    float hl = p.length / 2.0f;
    pts_[idx][0].x = (lv_value_precise_t)(cx + ux * hl);
    pts_[idx][0].y = (lv_value_precise_t)(cy + uy * hl);
    pts_[idx][1].x = (lv_value_precise_t)(cx - ux * hl);
    pts_[idx][1].y = (lv_value_precise_t)(cy - uy * hl);
    lv_line_set_points(eyes_[idx], pts_[idx], 2);
    lv_obj_set_style_line_width(eyes_[idx], (int32_t)(p.width + 0.5f), 0);
}

void GrokFace::Tick(uint32_t now) {
    float dt = (now - last_tick_) / 1000.0f;
    if (dt < 0 || dt > 0.5f) dt = 0.033f;
    last_tick_ = now;
    float t = now / 1000.0f;
    float since = (now - state_since_) / 1000.0f;

    bool sleeping = state_ == FaceState::kSleep;
    bool thinking = state_ == FaceState::kThinking || state_ == FaceState::kBusy;
    sleep_ = approach(sleep_, sleeping ? 1.f : 0.f, sleeping ? 2.5f : 8.f, dt);
    perk_ = approach(perk_, state_ == FaceState::kListening ? 1.f : 0.f, 10.f, dt);
    think_ = approach(think_, thinking ? 1.f : 0.f, 6.f, dt);
    float lvl_target = state_ == FaceState::kSpeaking ? audio_level_target_ : 0.f;
    audio_level_ = approach(audio_level_, lvl_target, lvl_target > audio_level_ ? 30.f : 12.f, dt);

    // ---- blink scheduling (idle, listening, speaking) ----
    if (!sleeping && !thinking && now >= next_blink_) {
        blink_start_ = now;
        double_blink_ = Rand01() < 0.2f;
        next_blink_ = now + 2500 + (uint32_t)(Rand01() * 4000);
    }
    float blink = 0;  // 0 open .. 1 closed
    {
        float bt = (now - blink_start_) / 1000.0f;
        const float dur = 0.16f;
        if (bt >= 0 && bt < dur) blink = sinf(bt / dur * (float)M_PI);
        else if (double_blink_ && bt >= dur + 0.08f && bt < 2 * dur + 0.08f)
            blink = sinf((bt - dur - 0.08f) / dur * (float)M_PI);
    }

    // ---- glances (idle only) ----
    if (state_ == FaceState::kIdle && now >= next_glance_) {
        float r = Rand01();
        if (r < 0.35f) { glance_target_x_ = 0; glance_target_y_ = 0; }
        else {
            glance_target_x_ = (Rand01() * 2 - 1) * 40.f;
            glance_target_y_ = (Rand01() * 2 - 1) * 18.f;
        }
        next_glance_ = now + 1800 + (uint32_t)(Rand01() * 3500);
    } else if (state_ != FaceState::kIdle) {
        glance_target_x_ = 0; glance_target_y_ = 0;
    }
    glance_x_ = approach(glance_x_, glance_target_x_, 9.f, dt);
    glance_y_ = approach(glance_y_, glance_target_y_, 9.f, dt);

    for (int i = 0; i < 2; i++) {
        float side = i == 0 ? -1.f : 1.f;
        EyePose p;
        p.dx = glance_x_;
        p.dy = glance_y_ + sinf(t * 1.6f) * 3.f;  // breathing
        p.length = (float)cfg_.eye_length;
        p.width = (float)cfg_.eye_width;
        p.angle = cfg_.tilt_deg;

        // listening: perk up - taller, a bit higher, slightly wider apart, pulse
        p.length += perk_ * (28.f + 6.f * sinf(t * 5.f));
        p.dy -= perk_ * 14.f;
        p.dx += perk_ * side * 6.f;
        p.width += perk_ * 6.f;

        // thinking: look up-right, eyes alternately squish, gentle sway
        {
            float phase = t * 3.2f + (i == 0 ? 0.f : 1.7f);
            p.dx += think_ * (28.f + 8.f * sinf(t * 1.3f));
            p.dy += think_ * (-26.f);
            p.length += think_ * (-30.f + 22.f * sinf(phase));
            p.angle += think_ * 6.f * sinf(t * 1.3f);
        }

        // speaking: bounce with level
        {
            float bounce = audio_level_;
            p.dy -= bounce * 22.f;
            p.length += bounce * 36.f - 10.f * (state_ == FaceState::kSpeaking ? 1.f : 0.f) * (1 - bounce);
            p.width += bounce * 6.f;
        }

        // blink: squash to a flat, almost horizontal bar
        float closed = blink > sleep_ ? blink : sleep_;
        if (closed > 0.001f) {
            p.length = lerp(p.length, 46.f, closed);
            p.width = lerp(p.width, 16.f, closed);
            p.angle = lerp(p.angle, 90.f - side * 4.f, closed);
            p.dy += closed * 22.f;
        }
        // sleep: slow droop
        p.dy += sleep_ * (12.f + 5.f * sinf(t * 0.9f));

        ApplyEye(i, p);
    }

    // sleeping "z z z" drifting up
    if (sleep_ > 0.6f) {
        float zt = fmodf(t, 3.0f) / 3.0f;
        lv_obj_remove_flag(zzz_, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_pos(zzz_, w_ / 2 + cfg_.eye_spacing / 2 + 30 + (int)(zt * 20), h_ / 2 - 70 - (int)(zt * 60));
        lv_obj_set_style_opa(zzz_, (lv_opa_t)(255 * (1 - zt) * clampf((sleep_ - 0.6f) * 2.5f, 0, 1)), 0);
    } else {
        lv_obj_add_flag(zzz_, LV_OBJ_FLAG_HIDDEN);
    }
    (void)since;
}
