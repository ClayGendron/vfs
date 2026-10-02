## sqlite — 800 files (4 × 20 × 10), write 0s, reindex 0s, median of 3 warm runs, limit 10

| caller | clauses | rare (25 files) | mid (2%) | half (50%) | common (~all) | mixed 4 words |
|---|---|---|---|---|---|---|
| whole (fast path) | whole | 6 ms · 10 stmts · 10 hits | 5 ms · 10 stmts · 10 hits | 9 ms · 10 stmts · 10 hits | 12 ms · 10 stmts · 10 hits | 12 ms · 10 stmts · 10 hits |
| 50% via 5 grants | 1 | 7 ms · 12 stmts · 10 hits | 6 ms · 12 stmts · 10 hits | 9 ms · 12 stmts · 10 hits | 14 ms · 12 stmts · 10 hits | 13 ms · 12 stmts · 10 hits |
| 50% via 40 grants | 1 | 14 ms · 12 stmts · 10 hits | 11 ms · 12 stmts · 10 hits | 14 ms · 12 stmts · 10 hits | 20 ms · 12 stmts · 10 hits | 18 ms · 12 stmts · 10 hits |
| 10% via 1 grant | 1 | 7 ms · 12 stmts · 10 hits | 7 ms · 12 stmts · 10 hits | 8 ms · 12 stmts · 10 hits | 11 ms · 12 stmts · 10 hits | 11 ms · 12 stmts · 10 hits |
| 10% via 8 grants | 1 | 7 ms · 12 stmts · 10 hits | 7 ms · 12 stmts · 10 hits | 10 ms · 12 stmts · 10 hits | 10 ms · 12 stmts · 10 hits | 11 ms · 12 stmts · 10 hits |
| 1 folder (0.1%) | 1 | 5 ms · 11 stmts · 10 hits | 5 ms · 11 stmts · 10 hits | 6 ms · 12 stmts · 10 hits | 8 ms · 12 stmts · 10 hits | 8 ms · 12 stmts · 10 hits |
