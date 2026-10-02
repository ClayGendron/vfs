## prefixes as rows vs arms as binds — sqlite, 50,000 chunks (10×100×50), dim 64

| caller | arms as binds (CTE) | prefixes as rows (range join) | same top 10 |
|---|---|---|---|
| 10% · 100 folder grants | 3.2 ms | 3.4 ms | True |
| 50% · 500 folder grants | 17.0 ms | 17.4 ms | True |
| 1% · 500 file grants | 1.5 ms | 1.3 ms | True |
| 10% · 5,000 file grants | refused: Expression tree is too large (maximum depth 1000) | 9.0 ms | — |
