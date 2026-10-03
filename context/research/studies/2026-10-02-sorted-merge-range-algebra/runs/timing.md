# Timing run

resolve = the resolver; pieces = `Rights.ranges()` (shipped) / `RangeRights.pieces()` (new). Total = both.

## holes (open root, H private homes), 1 member

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 1 ms | 97 ms | 98 ms | 3 ms | 0 ms | 3 ms | 2,804 / 2,804 |
| 10,000 | 13 ms | 16.3 s | 16.3 s | 34 ms | 3 ms | 37 ms | 28,004 / 28,004 |
| 100,000 | skipped: projected ~1632 s | | | 253 ms | 34 ms | 287 ms | – / 280,004 |

## postures (private root, H shared homes each with a private sub), 1 member

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 214 ms | 3 ms | 216 ms | 4 ms | 1 ms | 4 ms | 4,901 / 5,000 |
| 10,000 | 21.6 s | 27 ms | 21.6 s | 41 ms | 6 ms | 47 ms | 49,001 / 50,000 |
| 100,000 | skipped: projected ~2161 s | | | 554 ms | 65 ms | 619 ms | – / 500,000 |

## grants (G grants to one group), 1 member

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 2 ms | 1 ms | 3 ms | 2 ms | 0 ms | 2 ms | 1,901 / 2,000 |
| 10,000 | 20 ms | 11 ms | 31 ms | 17 ms | 2 ms | 20 ms | 19,001 / 20,000 |
| 100,000 | 252 ms | 114 ms | 366 ms | 255 ms | 27 ms | 282 ms | 190,001 / 200,000 |

## grants (G grants to one group), 2 members

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 300 ms | 1 ms | 301 ms | 5 ms | 0 ms | 5 ms | 1,901 / 2,000 |
| 10,000 | 26.0 s | 11 ms | 26.0 s | 55 ms | 2 ms | 57 ms | 19,001 / 20,000 |
| 100,000 | skipped: projected ~2600 s | | | 692 ms | 27 ms | 719 ms | – / 200,000 |

## grants (G grants to one group), 5 members

| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |
|---|---|---|---|---|---|---|---|
| 1,000 | 3.4 s | 1 ms | 3.4 s | 16 ms | 0 ms | 16 ms | 1,901 / 2,000 |
| 10,000 | skipped: projected ~340 s | | | 169 ms | 2 ms | 171 ms | – / 20,000 |
| 100,000 | skipped: projected ~34011 s | | | 1.9 s | 27 ms | 1.9 s | – / 200,000 |

## grants, 2 members with different prefixes (u1: /p/i, u2: /p/i/sub) — the meet keeps the deeper one

| n | shipped total | new total | pieces (shipped / new) |
|---|---|---|---|
| 1,000 | 264 ms | 6 ms | 2,000 / 2,000 |
| 10,000 | 26.2 s | 64 ms | 20,000 / 20,000 |
| 100,000 | skipped: projected ~2616 s | 798 ms | – / 200,000 |
