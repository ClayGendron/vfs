"""Count, under a deterministic fake clock, how far three check cadences overrun a deadline.

Each item costs one tick of CPU. The deadline falls at tick 1000. Three patterns:
  per-item     : read the clock before every item (trio checkpoint style; vfs verify.rs per body)
  every-N      : read the clock before every Nth item (vfs 64-item cadence; tokio's 128-op budget shape)
  timer-flag   : a timer thread sets a flag at the deadline; the loop reads the flag per item (anyio call_at / Go AfterFunc shape)
We count clock reads and items run past the deadline. No wall-clock number is produced.
"""
import sys

DEADLINE = 1000
ITEMS = 10_000

def per_item(cost):
    now = reads = done = 0
    for _ in range(ITEMS):
        reads += 1
        if now > DEADLINE:
            break
        now += cost; done += 1
    return reads, done

def every_n(cost, n):
    now = reads = done = 0
    for i in range(ITEMS):
        if i % n == 0:
            reads += 1
            if now > DEADLINE:
                break
        now += cost; done += 1
    return reads, done

def timer_flag(cost):
    # the timer fires between items at the first item boundary after the deadline; flag reads are not clock reads
    now = reads = done = 0
    flag = False
    for _ in range(ITEMS):
        if now > DEADLINE:
            flag = True  # the timer thread's set, modelled at the boundary
        if flag:
            break
        now += cost; done += 1
    return reads, done

for cost in (1, 7, 50):
    items_to_deadline = DEADLINE // cost + 1
    r, d = per_item(cost);        print(f"cost={cost:>3} per-item   clock_reads={r:>5} items_run={d:>5} overrun_items={d - items_to_deadline:>4}")
    for n in (64, 128):
        r, d = every_n(cost, n);  print(f"cost={cost:>3} every-{n:<3}  clock_reads={r:>5} items_run={d:>5} overrun_items={d - items_to_deadline:>4}")
    r, d = timer_flag(cost);      print(f"cost={cost:>3} timer-flag clock_reads={r:>5} items_run={d:>5} overrun_items={d - items_to_deadline:>4}")
