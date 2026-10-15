// Tamagroki cube glue shared between the face, audio path and board.
#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace tamagroki {
// Loudness (0..1) of the PCM currently being sent to the speaker.
// Written by AudioService's output task, read by the face timer.
extern std::atomic<float> g_playback_level;
void ReportPlaybackPcm(const int16_t* pcm, size_t samples);
}  // namespace tamagroki
