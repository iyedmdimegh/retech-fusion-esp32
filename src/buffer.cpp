#include "buffer.h"

#include <string.h>
#include <stdint.h>

#include "config.h"
#include "schema.h"  // for PAYLOAD_BUFFER_SIZE

namespace {

// Per-slot storage: 2 B length + payload data. Static-allocated to avoid
// heap fragmentation on long runs.
struct Entry {
    uint16_t len;                                  // 0 means slot is empty
    char     data[Schema::PAYLOAD_BUFFER_SIZE];
};

Entry  g_entries[RING_BUFFER_CAPACITY];
size_t g_head    = 0;   // index of oldest valid entry (read side)
size_t g_tail    = 0;   // index of next free slot     (write side)
size_t g_count   = 0;   // number of valid entries
size_t g_dropped = 0;   // running overflow counter

inline size_t advance(size_t i) {
    return (i + 1u) % RING_BUFFER_CAPACITY;
}

} // namespace

namespace MsgBuffer {

void begin() {
    for (size_t i = 0; i < RING_BUFFER_CAPACITY; ++i) {
        g_entries[i].len = 0;
    }
    g_head    = 0;
    g_tail    = 0;
    g_count   = 0;
    g_dropped = 0;
}

bool push(const char* payload, size_t len) {
    if (payload == nullptr || len == 0)                 return false;
    if (len > sizeof(g_entries[0].data))                return false;

    if (g_count == RING_BUFFER_CAPACITY) {
        // Buffer full — drop the oldest entry (FIFO overflow) so the newest
        // sample always lands. Tracked via g_dropped for telemetry.
        g_head = advance(g_head);
        g_count--;
        g_dropped++;
    }

    Entry& slot = g_entries[g_tail];
    memcpy(slot.data, payload, len);
    slot.len = (uint16_t)len;
    g_tail = advance(g_tail);
    g_count++;
    return true;
}

bool peekOldest(const char** out_payload, size_t* out_len) {
    if (g_count == 0 || out_payload == nullptr || out_len == nullptr) {
        return false;
    }
    const Entry& slot = g_entries[g_head];
    *out_payload = slot.data;
    *out_len     = slot.len;
    return true;
}

void popOldest() {
    if (g_count == 0) return;
    g_entries[g_head].len = 0;
    g_head = advance(g_head);
    g_count--;
}

size_t size()     { return g_count; }
size_t capacity() { return RING_BUFFER_CAPACITY; }
bool   isEmpty()  { return g_count == 0; }
bool   isFull()   { return g_count == RING_BUFFER_CAPACITY; }
size_t dropped()  { return g_dropped; }

} // namespace MsgBuffer
