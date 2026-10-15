// Headless LVGL simulator for the Tamagroki face. Renders each animation state
// to PPM frames (converted to PNG/GIF by render.py). No SDL needed.
#include <lvgl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <vector>
#include <math.h>
#include "grok_face.h"

static const int W = 480, H = 480;
static std::vector<uint8_t> fb(W * H * 4);
static uint32_t g_now = 0;
static uint32_t tick_cb() { return g_now; }

static void flush_cb(lv_display_t* d, const lv_area_t* a, uint8_t* px) {
    int w = lv_area_get_width(a);
    for (int y = a->y1; y <= a->y2; y++)
        memcpy(&fb[(y * W + a->x1) * 4], px + (y - a->y1) * w * 4, w * 4);
    lv_display_flush_ready(d);
}

static void save_ppm(const std::string& path) {
    FILE* f = fopen(path.c_str(), "wb");
    fprintf(f, "P6\n%d %d\n255\n", W, H);
    for (int i = 0; i < W * H; i++) { // XRGB8888 little-endian: B G R A
        uint8_t rgb[3] = {fb[i * 4 + 2], fb[i * 4 + 1], fb[i * 4 + 0]};
        fwrite(rgb, 1, 3, f);
    }
    fclose(f);
}

int main(int argc, char** argv) {
    const char* out = argc > 1 ? argv[1] : "out";
    uint32_t bg = argc > 2 ? strtoul(argv[2], nullptr, 16) : 0x9B7FE0;
    lv_init();
    lv_tick_set_cb(tick_cb);
    lv_display_t* disp = lv_display_create(W, H);
    static std::vector<uint8_t> buf(W * H * 4);
    lv_display_set_buffers(disp, buf.data(), nullptr, buf.size(), LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_flush_cb(disp, flush_cb);

    FaceConfig cfg;
    cfg.bg_color = bg;
    GrokFace face;
    face.Create(lv_screen_active(), W, H, cfg);

    struct Seg { FaceState s; int ms; };
    // a scripted "conversation" timeline
    std::vector<Seg> script = {
        {FaceState::kIdle, 7000}, {FaceState::kListening, 2500}, {FaceState::kThinking, 2500},
        {FaceState::kSpeaking, 4000}, {FaceState::kIdle, 1500}, {FaceState::kSleep, 4000},
    };
    const int frame_ms = 40;  // 25 fps
    int frame = 0;
    char path[512];
    FILE* index = fopen((std::string(out) + "/frames.csv").c_str(), "w");
    for (auto& seg : script) {
        face.SetState(seg.s, g_now);
        for (int t = 0; t < seg.ms; t += frame_ms, g_now += frame_ms) {
            if (seg.s == FaceState::kSpeaking) {
                // fake syllable envelope ~ 4-6 Hz
                float x = g_now / 1000.0f;
                float lvl = fabsf(sinf(x * 13.f)) * (0.55f + 0.45f * sinf(x * 2.3f));
                face.SetAudioLevel(lvl);
            }
            face.Tick(g_now);
            lv_timer_handler();
            lv_refr_now(disp);
            snprintf(path, sizeof(path), "%s/f%05d.ppm", out, frame);
            save_ppm(path);
            fprintf(index, "%d,%s,%u\n", frame, FaceStateName(seg.s), g_now);
            frame++;
        }
    }
    fclose(index);
    printf("rendered %d frames to %s\n", frame, out);
    return 0;
}
