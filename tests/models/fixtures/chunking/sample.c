/* A fixture translation unit: functions, a struct, and comment gaps. */

#include <stddef.h>

struct ring {
    size_t head;
    size_t tail;
    size_t capacity;
    int slots[64];
};

/* Interstitial comments become gap spans between named siblings. */

static size_t ring_advance(size_t index, size_t capacity)
{
    return (index + 1 == capacity) ? 0 : index + 1;
}

int ring_push(struct ring *r, int value)
{
    size_t next = ring_advance(r->head, r->capacity);
    if (next == r->tail) {
        return -1; /* full */
    }
    r->slots[r->head] = value;
    r->head = next;
    return 0;
}

int ring_pop(struct ring *r, int *out)
{
    if (r->tail == r->head) {
        return -1; /* empty */
    }
    *out = r->slots[r->tail];
    r->tail = ring_advance(r->tail, r->capacity);
    return 0;
}

size_t ring_count(const struct ring *r)
{
    if (r->head >= r->tail) {
        return r->head - r->tail;
    }
    return r->capacity - (r->tail - r->head);
}
