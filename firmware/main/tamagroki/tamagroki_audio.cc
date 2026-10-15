#include <stddef.h>
#include <stdint.h>
#include <math.h>
#include "tamagroki.h"

namespace tamagroki {
std::atomic<float> g_playback_level{0.0f};

void ReportPlaybackPcm(const int16_t* pcm, size_t samples) {
    if (samples == 0) return;
    double acc = 0;
    for (size_t i = 0; i < samples; i++) acc += (double)pcm[i] * pcm[i];
    float rms = sqrtf((float)(acc / samples)) / 32768.0f;
    // map ~-40 dBFS..-6 dBFS onto 0..1
    float db = 20.0f * log10f(rms + 1e-6f);
    float lvl = (db + 40.0f) / 34.0f;
    g_playback_level.store(lvl < 0 ? 0 : (lvl > 1 ? 1 : lvl), std::memory_order_relaxed);
}
}  // namespace tamagroki
