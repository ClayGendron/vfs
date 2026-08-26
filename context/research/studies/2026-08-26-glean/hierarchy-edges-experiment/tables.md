Setup: 977 nodes (779 files, 198 directories incl. root), 976 fs edges, 864 reference edges (691 markdown, 173 import) touching 394 nodes; max depth 7, max fan-out 113; extraction 0.168 s.

### Agreement with R (Spearman/Kendall)

| config | in-deg ref | in-deg all | in-deg files | PR ref | PR all | PR files | Katz ref | Katz all | Katz files | PR vs T all | Katz vs T all |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | — | — |
| T[down] | n/a (const) | 0.02/0.02 | n/a (const) | -0.41/-0.30 | -0.19/-0.14 | -0.30/-0.23 | -0.28/-0.22 | -0.20/-0.17 | -0.28/-0.24 | 1.00/1.00 | 1.00/1.00 |
| T[up] | n/a (const) | -0.30/-0.28 | n/a (const) | n/a (const) | -0.30/-0.27 | n/a (const) | n/a (const) | -0.30/-0.27 | n/a (const) | 1.00/1.00 | 1.00/1.00 |
| T[both] | n/a (const) | -0.30/-0.28 | n/a (const) | -0.47/-0.34 | -0.45/-0.35 | -0.35/-0.27 | 0.07/0.05 | 0.04/0.04 | 0.27/0.21 | 1.00/1.00 | 1.00/1.00 |
| H(0.05)[down] | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 0.85/0.75 | 0.72/0.62 | 0.75/0.65 | 0.99/0.97 | 0.80/0.74 | 0.86/0.81 | 0.44/0.47 | 0.34/0.36 |
| H(0.1)[down] | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 0.85/0.75 | 0.72/0.62 | 0.75/0.65 | 0.99/0.97 | 0.80/0.74 | 0.86/0.81 | 0.44/0.47 | 0.34/0.36 |
| H(0.25)[down] | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 0.85/0.75 | 0.72/0.62 | 0.75/0.65 | 0.99/0.97 | 0.80/0.74 | 0.86/0.81 | 0.44/0.47 | 0.34/0.36 |
| H(0.5)[down] | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 0.85/0.75 | 0.72/0.62 | 0.75/0.65 | 0.99/0.97 | 0.80/0.74 | 0.86/0.81 | 0.44/0.47 | 0.34/0.36 |
| H(1.0)[down] | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 0.85/0.75 | 0.72/0.62 | 0.75/0.65 | 0.99/0.97 | 0.80/0.74 | 0.86/0.81 | 0.44/0.47 | 0.34/0.36 |
| H(0.05)[up] | 1.00/1.00 | 0.84/0.80 | 1.00/1.00 | 1.00/0.99 | 0.65/0.63 | 1.00/1.00 | 1.00/1.00 | 0.84/0.81 | 1.00/1.00 | 0.49/0.45 | 0.25/0.26 |
| H(0.1)[up] | 1.00/1.00 | 0.83/0.79 | 1.00/1.00 | 1.00/0.99 | 0.65/0.63 | 1.00/1.00 | 1.00/1.00 | 0.83/0.80 | 1.00/1.00 | 0.50/0.45 | 0.26/0.27 |
| H(0.25)[up] | 1.00/1.00 | 0.79/0.76 | 1.00/1.00 | 1.00/0.98 | 0.63/0.61 | 1.00/0.99 | 1.00/1.00 | 0.81/0.77 | 1.00/1.00 | 0.52/0.47 | 0.30/0.30 |
| H(0.5)[up] | 1.00/1.00 | 0.74/0.71 | 1.00/1.00 | 1.00/0.96 | 0.61/0.59 | 1.00/0.98 | 1.00/1.00 | 0.77/0.73 | 1.00/1.00 | 0.55/0.50 | 0.36/0.34 |
| H(1.0)[up] | 1.00/1.00 | 0.65/0.63 | 1.00/1.00 | 0.99/0.93 | 0.56/0.54 | 1.00/0.97 | 1.00/1.00 | 0.72/0.69 | 1.00/1.00 | 0.60/0.54 | 0.43/0.40 |
| H(0.05)[both] | 1.00/1.00 | 0.84/0.80 | 1.00/1.00 | 0.89/0.74 | 0.38/0.31 | 0.55/0.44 | 0.98/0.94 | 0.78/0.68 | 0.85/0.76 | -0.06/-0.06 | 0.39/0.29 |
| H(0.1)[both] | 1.00/1.00 | 0.83/0.79 | 1.00/1.00 | 0.89/0.74 | 0.38/0.31 | 0.56/0.45 | 0.98/0.92 | 0.77/0.67 | 0.85/0.75 | -0.07/-0.06 | 0.41/0.31 |
| H(0.25)[both] | 1.00/1.00 | 0.79/0.76 | 1.00/1.00 | 0.88/0.73 | 0.38/0.31 | 0.56/0.46 | 0.93/0.82 | 0.70/0.59 | 0.82/0.70 | -0.07/-0.06 | 0.53/0.40 |
| H(0.5)[both] | 1.00/1.00 | 0.74/0.71 | 1.00/1.00 | 0.88/0.72 | 0.37/0.30 | 0.57/0.46 | 0.84/0.70 | 0.59/0.49 | 0.78/0.65 | -0.06/-0.06 | 0.69/0.55 |
| H(1.0)[both] | 1.00/1.00 | 0.65/0.63 | 1.00/1.00 | 0.87/0.70 | 0.36/0.29 | 0.58/0.46 | 0.74/0.58 | 0.48/0.39 | 0.73/0.59 | -0.02/-0.03 | 0.83/0.68 |

### Top-25 profile (directories in top-25 / mean depth / mean parent fan-out / overlap with R's top-25)

| config | in-deg | PR | Katz |
|---|---|---|---|
| R | 0 / 3.12 / 58.6 / 25 | 0 / 3.28 / 69.4 / 25 | 0 / 3.48 / 74.8 / 25 |
| T[down] | 2 / 2.84 / 45.8 / 0 | 3 / 4.68 / 1.0 / 0 | 1 / 6.52 / 11.1 / 0 |
| T[up] | 25 / 3.16 / 14.4 / 0 | 25 / 2.76 / 18.0 / 0 | 25 / 2.68 / 18.1 / 0 |
| T[both] | 25 / 3.16 / 14.4 / 0 | 25 / 3.28 / 18.6 / 0 | 25 / 3.56 / 91.7 / 0 |
| H(0.05)[down] | 0 / 3.12 / 58.6 / 25 | 0 / 3.24 / 68.9 / 23 | 0 / 3.48 / 74.8 / 25 |
| H(0.1)[down] | 0 / 3.12 / 58.6 / 25 | 0 / 3.24 / 68.9 / 23 | 0 / 3.48 / 74.8 / 25 |
| H(0.25)[down] | 0 / 3.12 / 58.6 / 25 | 0 / 3.24 / 68.9 / 23 | 0 / 3.48 / 74.8 / 25 |
| H(0.5)[down] | 0 / 3.12 / 58.6 / 25 | 0 / 3.24 / 68.9 / 23 | 0 / 3.48 / 74.8 / 25 |
| H(1.0)[down] | 0 / 3.12 / 58.6 / 25 | 0 / 3.24 / 68.9 / 23 | 0 / 3.48 / 74.8 / 25 |
| H(0.05)[up] | 0 / 3.12 / 58.6 / 25 | 19 / 2.48 / 29.5 / 6 | 0 / 3.48 / 74.8 / 25 |
| H(0.1)[up] | 2 / 3.12 / 58.2 / 23 | 20 / 2.44 / 29.6 / 5 | 1 / 3.4 / 74.9 / 24 |
| H(0.25)[up] | 3 / 3.08 / 58.4 / 22 | 21 / 2.44 / 25.4 / 4 | 2 / 3.4 / 70.6 / 23 |
| H(0.5)[up] | 9 / 3.12 / 46.6 / 16 | 24 / 2.6 / 14.0 / 1 | 4 / 3.12 / 70.1 / 21 |
| H(1.0)[up] | 17 / 3.0 / 30.2 / 8 | 24 / 2.6 / 14.0 / 1 | 6 / 3.08 / 70.4 / 19 |
| H(0.05)[both] | 0 / 3.12 / 58.6 / 25 | 18 / 2.88 / 26.2 / 7 | 0 / 3.48 / 74.8 / 25 |
| H(0.1)[both] | 2 / 3.12 / 58.2 / 23 | 18 / 2.88 / 26.2 / 7 | 1 / 3.4 / 74.9 / 24 |
| H(0.25)[both] | 3 / 3.08 / 58.4 / 22 | 20 / 3.08 / 26.3 / 5 | 2 / 3.4 / 74.5 / 23 |
| H(0.5)[both] | 9 / 3.12 / 46.6 / 16 | 22 / 3.0 / 18.3 / 3 | 2 / 3.16 / 86.1 / 20 |
| H(1.0)[both] | 17 / 3.0 / 30.2 / 8 | 24 / 3.0 / 15.1 / 1 | 5 / 2.8 / 90.2 / 17 |

### Structure correlations (Spearman of score with depth over files, parent fan-out over files, own fan-out over directories)

| config | in-deg depth/pfan/dirfan | PR depth/pfan/dirfan | Katz depth/pfan/dirfan |
|---|---|---|---|
| R | -0.30 / +0.32 / n/a | -0.30 / +0.30 / n/a | -0.28 / +0.32 / n/a |
| T[down] | n/a / n/a / -0.09 | +0.45 / -0.99 / +0.39 | +1.00 / -0.46 / -0.25 |
| T[up] | n/a / n/a / +1.00 | n/a / n/a / +0.95 | n/a / n/a / +0.95 |
| T[both] | n/a / n/a / +1.00 | +0.52 / -0.83 / +0.96 | -0.31 / +0.45 / +0.07 |
| H(0.05)[down] | -0.30 / +0.32 / -0.09 | -0.08 / -0.27 / +0.39 | +0.17 / +0.16 / -0.25 |
| H(0.1)[down] | -0.30 / +0.32 / -0.09 | -0.08 / -0.27 / +0.39 | +0.17 / +0.16 / -0.25 |
| H(0.25)[down] | -0.30 / +0.32 / -0.09 | -0.08 / -0.27 / +0.39 | +0.17 / +0.16 / -0.25 |
| H(0.5)[down] | -0.30 / +0.32 / -0.09 | -0.08 / -0.27 / +0.39 | +0.17 / +0.16 / -0.25 |
| H(1.0)[down] | -0.30 / +0.32 / -0.09 | -0.08 / -0.27 / +0.39 | +0.17 / +0.16 / -0.25 |
| H(0.05)[up] | -0.30 / +0.32 / +1.00 | -0.30 / +0.30 / +0.81 | -0.28 / +0.32 / +0.98 |
| H(0.1)[up] | -0.30 / +0.32 / +1.00 | -0.30 / +0.31 / +0.81 | -0.28 / +0.32 / +0.98 |
| H(0.25)[up] | -0.30 / +0.32 / +1.00 | -0.30 / +0.31 / +0.83 | -0.28 / +0.32 / +0.98 |
| H(0.5)[up] | -0.30 / +0.32 / +1.00 | -0.31 / +0.31 / +0.83 | -0.28 / +0.32 / +0.98 |
| H(1.0)[up] | -0.30 / +0.32 / +1.00 | -0.31 / +0.31 / +0.85 | -0.28 / +0.32 / +0.97 |
| H(0.05)[both] | -0.30 / +0.32 / +1.00 | -0.29 / +0.33 / +0.78 | -0.38 / +0.67 / +0.94 |
| H(0.1)[both] | -0.30 / +0.32 / +1.00 | -0.30 / +0.35 / +0.79 | -0.39 / +0.68 / +0.90 |
| H(0.25)[both] | -0.30 / +0.32 / +1.00 | -0.33 / +0.37 / +0.80 | -0.39 / +0.70 / +0.72 |
| H(0.5)[both] | -0.30 / +0.32 / +1.00 | -0.35 / +0.40 / +0.81 | -0.40 / +0.67 / +0.39 |
| H(1.0)[both] | -0.30 / +0.32 / +1.00 | -0.36 / +0.41 / +0.83 | -0.41 / +0.56 / +0.13 |

### Coverage: fraction of nodes at the score floor (all nodes / files only)

| config | in-deg | PR | Katz |
|---|---|---|---|
| R | 0.721 / 0.650 | 0.721 / 0.650 | 0.721 / 0.650 |
| T[down] | 0.001 / 1.000 | 0.001 / 0.141 | 0.001 / 0.051 |
| T[up] | 0.799 / 1.000 | 0.799 / 1.000 | 0.799 / 1.000 |
| T[both] | 0.799 / 1.000 | 0.003 / 0.004 | 0.001 / 0.001 |
| H(0.05)[down] | 0.001 / 0.650 | 0.001 / 0.031 | 0.001 / 0.040 |
| H(0.1)[down] | 0.001 / 0.650 | 0.001 / 0.031 | 0.001 / 0.040 |
| H(0.25)[down] | 0.001 / 0.650 | 0.001 / 0.031 | 0.001 / 0.040 |
| H(0.5)[down] | 0.001 / 0.650 | 0.001 / 0.031 | 0.001 / 0.040 |
| H(1.0)[down] | 0.001 / 0.650 | 0.001 / 0.031 | 0.001 / 0.040 |
| H(0.05)[up] | 0.520 / 0.650 | 0.520 / 0.650 | 0.520 / 0.650 |
| H(0.1)[up] | 0.520 / 0.650 | 0.520 / 0.650 | 0.520 / 0.650 |
| H(0.25)[up] | 0.520 / 0.650 | 0.520 / 0.650 | 0.520 / 0.650 |
| H(0.5)[up] | 0.520 / 0.650 | 0.520 / 0.650 | 0.520 / 0.650 |
| H(1.0)[up] | 0.520 / 0.650 | 0.520 / 0.650 | 0.520 / 0.650 |
| H(0.05)[both] | 0.520 / 0.650 | 0.031 / 0.039 | 0.001 / 0.001 |
| H(0.1)[both] | 0.520 / 0.650 | 0.031 / 0.039 | 0.001 / 0.001 |
| H(0.25)[both] | 0.520 / 0.650 | 0.031 / 0.039 | 0.001 / 0.001 |
| H(0.5)[both] | 0.520 / 0.650 | 0.001 / 0.001 | 0.001 / 0.001 |
| H(1.0)[both] | 0.520 / 0.650 | 0.001 / 0.001 | 0.001 / 0.001 |

### Does w matter? H(0.05) vs H(1.0), same direction (Spearman/Kendall)

| direction | in-deg all / files | PR all / files | Katz all / files |
|---|---|---|---|
| down | 1.00/1.00 / 1.00/1.00 | 1.00/1.00 / 1.00/1.00 | 1.00/1.00 / 1.00/1.00 |
| up | 0.95/0.87 / 1.00/1.00 | 0.99/0.92 / 1.00/0.98 | 0.97/0.91 / 1.00/1.00 |
| both | 0.95/0.87 / 1.00/1.00 | 0.94/0.86 / 0.95/0.87 | 0.77/0.58 / 0.79/0.62 |

### Top-10 under selected configurations

- **R, PR**: `context/open-questions.md` d2; `context/research/2026-08-25-set-based-scattered-delete.md` d3; `context/research/2026-08-25-mysql-family-batch-update-shapes.md` d3; `docs/reference/glob-patterns.md` d3; `context/specs/archive/031-unified-entry-creation-chokepoint/design.md` d5; `docs/explanation/glob-language.md` d3; `context/specs/archive/031-unified-entry-creation-chokepoint/explanation.md` d5; `context/research/2026-07-13-database-storage-write-pipeline.md` d3; `context/research/2026-08-25-remediation-round-landing-review.md` d3; `context/research/2026-07-13-database-storage-backend.md` d3
- **R, in-deg**: `context/open-questions.md` d2; `src/vfs/paths.py` d3; `context/research/2026-07-13-database-storage-write-pipeline.md` d3; `src/vfs/results/__init__.py` d4; `context/research/2026-07-13-database-storage-grep-index.md` d3; `context/research/2026-08-26-glean-brief.md` d3; `src/vfs/models/__init__.py` d4; `context/research/2026-07-13-database-storage-backend.md` d3; `context/specs/STATUS.md` d3; `context/research/2026-07-13-database-storage-pipelines-brief.md` d3
- **T[down], PR**: `context/research/studies/2026-08-12-posting-path-rust-kernel/vfs_postings_rs/src/lib.rs` d7; `context/research/studies/2026-08-17-verify-authority-spike/rust/src/main.rs` d7; `crates/vfs-core` (dir) d2; `src/vfs` (dir) d2; `context/product/home-doc-section-1-arc.md` d3; `context/specs/active/045-verb-wire-contract/spec.md` d5; `context/specs/active/051-fanout-deadline-budget/spec.md` d5; `context/specs/active/054-mcp-serve-locks-topology/spec.md` d5; `context/specs/active/058-row-level-permission-grants/spec.md` d5; `context/specs/active/067-graph-traversal-only/spec.md` d5
- **T[down], Katz**: `context/research/studies/2026-08-12-posting-path-rust-kernel/vfs_postings_rs/src/lib.rs` d7; `context/research/studies/2026-08-17-verify-authority-spike/rust/src/main.rs` d7; `context/research/studies/2026-08-26-glean/lexical-leg/results/log-linux-1000.txt` d7; `context/research/studies/2026-08-26-glean/lexical-leg/results/log-linux-10000.txt` d7; `context/research/studies/2026-08-26-glean/lexical-leg/results/rankings-linux-10000.json` d7; `context/research/studies/2026-08-26-glean/lexical-leg/results/rankings-vfs.json` d7; `context/research/studies/2026-08-26-glean/lexical-leg/results/report-linux-1000.json` d7; `context/research/studies/2026-08-26-glean/lexical-leg/results/report-linux-10000.json` d7; `context/research/studies/2026-08-26-glean/lexical-leg/results/report-vfs.json` d7; `context/research/studies/2026-08-26-glean/lexical-leg/results/scope-plans-analyze.txt` d7
- **T[up], PR**: `.` (dir) d0; `context` (dir) d1; `context/specs/archive` (dir) d3; `context/research` (dir) d2; `context/specs` (dir) d2; `context/research/studies` (dir) d3; `context/research/studies/2026-08-26-glean` (dir) d4; `tests` (dir) d1; `docs` (dir) d1; `context/decisions` (dir) d2
- **H(0.1)[down], PR**: `context/open-questions.md` d2; `context/research/2026-08-25-set-based-scattered-delete.md` d3; `context/research/2026-08-25-mysql-family-batch-update-shapes.md` d3; `docs/reference/glob-patterns.md` d3; `context/specs/archive/031-unified-entry-creation-chokepoint/design.md` d5; `docs/explanation/glob-language.md` d3; `context/specs/archive/031-unified-entry-creation-chokepoint/explanation.md` d5; `context/research/2026-08-25-remediation-round-landing-review.md` d3; `context/research/2026-07-13-database-storage-write-pipeline.md` d3; `context/research/2026-07-13-database-storage-backend.md` d3
- **H(0.1)[down], Katz**: `context/research/2026-07-13-database-storage-write-pipeline.md` d3; `context/research/2026-07-13-database-storage-grep-index.md` d3; `context/research/2026-07-13-database-storage-backend.md` d3; `context/research/2026-07-13-database-storage-pipelines-brief.md` d3; `context/research/2026-07-13-database-storage-read-pipeline.md` d3; `context/research/2026-07-14-database-storage-posting-storage.md` d3; `context/open-questions.md` d2; `context/research/2026-08-26-glean-brief.md` d3; `context/specs/archive/072-database-storage-backend/spike-results-pipelines.md` d5; `context/research/2026-08-26-glean-in-the-engine.md` d3
- **H(0.1)[up], PR**: `.` (dir) d0; `context` (dir) d1; `context/research` (dir) d2; `context/specs/archive` (dir) d3; `context/specs` (dir) d2; `context/research/studies` (dir) d3; `docs` (dir) d1; `context/research/studies/2026-08-26-glean` (dir) d4; `tests` (dir) d1; `context/open-questions.md` d2
- **H(0.5)[up], in-deg**: `context/specs/archive` (dir) d3; `context/research` (dir) d2; `context/open-questions.md` d2; `context/decisions` (dir) d2; `src/vfs/paths.py` d3; `context/research/2026-07-13-database-storage-write-pipeline.md` d3; `src/vfs/results/__init__.py` d4; `docs/plans` (dir) d2; `context/research/studies/2026-08-17-search-storage-organizations` (dir) d4; `context/research/2026-07-13-database-storage-grep-index.md` d3
- **H(0.1)[both], PR**: `context/research` (dir) d2; `context/specs/archive` (dir) d3; `context/research/studies/2026-08-17-search-storage-organizations` (dir) d4; `context/open-questions.md` d2; `docs/plans` (dir) d2; `scripts` (dir) d1; `context/research/studies/2026-08-26-glean/engine-matrix` (dir) d5; `docs` (dir) d1; `context/research/studies/2026-08-25-set-based-topology-statements/results` (dir) d5; `context/research/2026-08-25-set-based-scattered-delete.md` d3
- **H(0.5)[both], Katz**: `context/research` (dir) d2; `context/research/2026-07-13-database-storage-write-pipeline.md` d3; `context/research/2026-07-13-database-storage-grep-index.md` d3; `context/research/2026-07-13-database-storage-backend.md` d3; `context/research/2026-07-14-database-storage-posting-storage.md` d3; `context/research/2026-07-13-database-storage-read-pipeline.md` d3; `context/research/2026-07-13-database-storage-pipelines-brief.md` d3; `context/research/2026-08-26-glean-brief.md` d3; `context/open-questions.md` d2; `context/research/2026-08-26-glean-in-the-engine.md` d3

### Sanity check: BM25 alone vs BM25 x (1 + beta * prior), 10 queries, 780 text files

| prior | beta | MRR | nDCG@5 |
|---|---|---|---|
| (none) | — | 0.414 | 0.270 |
| pagerank [R] | 0.15 | 0.403 | 0.246 |
| pagerank [R] | 0.5 | 0.403 | 0.249 |
| in_degree [R] | 0.15 | 0.412 | 0.279 |
| in_degree [R] | 0.5 | 0.431 | 0.284 |
| pagerank [T[down]] | 0.15 | 0.267 | 0.188 |
| pagerank [T[down]] | 0.5 | 0.205 | 0.123 |
| in_degree [T[down]] | 0.15 | 0.414 | 0.270 |
| in_degree [T[down]] | 0.5 | 0.414 | 0.270 |
| pagerank [T[up]] | 0.15 | 0.414 | 0.270 |
| pagerank [T[up]] | 0.5 | 0.414 | 0.270 |
| in_degree [T[up]] | 0.15 | 0.414 | 0.270 |
| in_degree [T[up]] | 0.5 | 0.414 | 0.270 |
| pagerank [H(0.1)[down]] | 0.15 | 0.401 | 0.243 |
| pagerank [H(0.1)[down]] | 0.5 | 0.380 | 0.255 |
| in_degree [H(0.1)[down]] | 0.15 | 0.426 | 0.312 |
| in_degree [H(0.1)[down]] | 0.5 | 0.435 | 0.312 |
| pagerank [H(0.5)[down]] | 0.15 | 0.401 | 0.243 |
| pagerank [H(0.5)[down]] | 0.5 | 0.380 | 0.255 |
| in_degree [H(0.5)[down]] | 0.15 | 0.412 | 0.279 |
| in_degree [H(0.5)[down]] | 0.5 | 0.431 | 0.284 |
| pagerank [H(0.1)[up]] | 0.15 | 0.403 | 0.252 |
| pagerank [H(0.1)[up]] | 0.5 | 0.403 | 0.249 |
| in_degree [H(0.1)[up]] | 0.15 | 0.412 | 0.279 |
| in_degree [H(0.1)[up]] | 0.5 | 0.431 | 0.284 |
| pagerank [H(0.1)[both]] | 0.15 | 0.385 | 0.237 |
| pagerank [H(0.1)[both]] | 0.5 | 0.375 | 0.231 |
| in_degree [H(0.1)[both]] | 0.15 | 0.426 | 0.312 |
| in_degree [H(0.1)[both]] | 0.5 | 0.435 | 0.312 |

### Timings (seconds, single process, Apple Silicon)

| config | edges | in-deg | PageRank | lambda_max (dense eig) | Katz (solve) | total |
|---|---|---|---|---|---|---|
| R | 864 | 0.0003 | 0.0071 | 0.010 | 0.0131 | 0.030 |
| T[down] | 976 | 0.0003 | 0.0022 | 0.003 | 0.0106 | 0.016 |
| T[up] | 976 | 0.0003 | 0.0016 | 0.006 | 0.0109 | 0.018 |
| T[both] | 1952 | 0.0003 | 0.0029 | 0.159 | 0.0107 | 0.173 |
| H(0.05)[down] | 1840 | 0.0003 | 0.0036 | 0.010 | 0.0107 | 0.024 |
| H(0.1)[down] | 1840 | 0.0003 | 0.0035 | 0.010 | 0.0107 | 0.025 |
| H(0.25)[down] | 1840 | 0.0003 | 0.0035 | 0.010 | 0.0107 | 0.025 |
| H(0.5)[down] | 1840 | 0.0003 | 0.0043 | 0.010 | 0.0107 | 0.025 |
| H(1.0)[down] | 1840 | 0.0003 | 0.0035 | 0.010 | 0.0107 | 0.024 |
| H(0.05)[up] | 1840 | 0.0003 | 0.0023 | 0.012 | 0.0106 | 0.025 |
| H(0.1)[up] | 1840 | 0.0003 | 0.0022 | 0.012 | 0.0106 | 0.025 |
| H(0.25)[up] | 1840 | 0.0003 | 0.0021 | 0.012 | 0.0105 | 0.025 |
| H(0.5)[up] | 1840 | 0.0003 | 0.0020 | 0.012 | 0.0113 | 0.025 |
| H(1.0)[up] | 1840 | 0.0003 | 0.0020 | 0.012 | 0.0106 | 0.025 |
| H(0.05)[both] | 2816 | 0.0004 | 0.0032 | 0.161 | 0.0114 | 0.176 |
| H(0.1)[both] | 2816 | 0.0004 | 0.0030 | 0.170 | 0.0118 | 0.185 |
| H(0.25)[both] | 2816 | 0.0004 | 0.0033 | 0.173 | 0.0116 | 0.188 |
| H(0.5)[both] | 2816 | 0.0003 | 0.0031 | 0.168 | 0.0114 | 0.182 |
| H(1.0)[both] | 2816 | 0.0003 | 0.0030 | 0.164 | 0.0114 | 0.178 |
