#pragma once

#include <Arduino.h>
#include <stddef.h>

namespace MsgBuffer {

// Reset the buffer (called once at boot).
void begin();

// Enqueue a payload at the tail. Returns false if the payload is empty or
// larger than the slot size. If the buffer is full, the oldest entry is
// silently dropped to make room (FIFO overflow), and dropped() increments.
bool push(const char* payload, size_t len);

// Inspect the oldest entry without removing it. Returns false if empty.
// On success, *out_payload points into static storage and *out_len is its
// byte length (no NUL guarantee — treat as binary).
bool peekOldest(const char** out_payload, size_t* out_len);

// Remove the oldest entry. No-op if empty.
void popOldest();

size_t size();        // entries currently buffered
size_t capacity();    // max entries (== RING_BUFFER_CAPACITY)
bool   isEmpty();
bool   isFull();
size_t dropped();     // running counter of overflow drops since boot

} // namespace MsgBuffer
