## sqlite — 50,000 files (10 × 100 × 50), write 12s, reindex 20s, median of 5 warm runs, limit 10

| caller | clauses | rare (25 files) | mid (2%) | half (50%) | common (~all) | mixed 4 words |
|---|---|---|---|---|---|---|
| whole (fast path) | whole | 45 ms · 10 stmts · 10 hits | 54 ms · 10 stmts · 10 hits | 58 ms · 11 stmts · 10 hits | 61 ms · 11 stmts · 10 hits | 63 ms · 11 stmts · 10 hits |
| 50% via 5 grants | 1 | 68 ms · 12 stmts · 10 hits | 80 ms · 12 stmts · 10 hits | 160 ms · 12 stmts · 10 hits | 249 ms · 13 stmts · 10 hits | 239 ms · 13 stmts · 10 hits |
| 50% via 500 grants | 3 | 2041 ms · 16 stmts · 10 hits | 2048 ms · 16 stmts · 10 hits | 2218 ms · 16 stmts · 10 hits | 2234 ms · 17 stmts · 10 hits | 2248 ms · 17 stmts · 10 hits |
| 10% via 1 grant | 1 | 42 ms · 12 stmts · 10 hits | 45 ms · 12 stmts · 10 hits | 138 ms · 12 stmts · 10 hits | 211 ms · 13 stmts · 10 hits | 216 ms · 13 stmts · 10 hits |
| 10% via 100 grants | 1 | 440 ms · 12 stmts · 10 hits | 443 ms · 12 stmts · 10 hits | 534 ms · 12 stmts · 10 hits | 603 ms · 13 stmts · 10 hits | 601 ms · 13 stmts · 10 hits |
| 1 folder (0.1%) | 1 | 36 ms · 11 stmts · 10 hits | 43 ms · 12 stmts · 10 hits | 124 ms · 12 stmts · 10 hits | 194 ms · 13 stmts · 10 hits | 199 ms · 13 stmts · 10 hits |
