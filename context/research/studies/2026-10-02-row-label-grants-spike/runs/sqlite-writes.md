## sqlite — writes: 1,000-user world plus /mid (1,000 rows), /mv (10,000), /big (1,000,000); 1,034,116 entries

| operation | statement shape | statements | rows touched | total ms (median of runs) | labels after |
|---|---|---|---|---|---|
| posture /mid → shared (1,000 rows) | 1 points + 1 open ranges (0 deeper postures cut); range join, <=500 pieces/statement | 2 | 1,001 | 3 | all correct |
| posture /mid → shared, chunked | 1 points + 1 open ranges (0 deeper postures cut); keyset chunks of 500 rows | 7 | 1,001 | 5 | all correct |
| posture /big → shared (1,000,000 rows) | 1 points + 1 open ranges (0 deeper postures cut); range join, <=500 pieces/statement | 2 | 1,000,001 | 1,962 | all correct |
| posture /big → shared, chunked | 1 points + 1 open ranges (0 deeper postures cut); keyset chunks of 50,000 rows | 43 | 1,000,001 | 1,433 | all correct |
| posture /big → shared, chunked | 1 points + 1 open ranges (0 deeper postures cut); keyset chunks of 200,000 rows | 13 | 1,000,001 | 1,829 | all correct |
| posture / → shared (root minus every deeper posture) | 1103 points + 2205 open ranges (1,102 deeper postures cut); range join, <=500 pieces/statement | 8 | 12,014 | 70 | all correct |
| posture / → shared, chunked | 1103 points + 2205 open ranges (1,102 deeper postures cut); keyset chunks of 50,000 rows | 4,413 | 12,014 | 810 | all correct |
| domain variant: posture /mid (1,000 rows) | `domain_id = :d` | 1 | 1,001 | 3 | all correct |
| domain variant: posture /big (1,000,000 rows) | `domain_id = :d` | 1 | 1,000,001 | 1,736 | all correct |
| grant at a new prefix over /big: public_level variant | no row write | 0 | 0 | 0 | n/a |
| grant at a new prefix over /big: domain variant | `path` range | 1 | 1,000,000 | 758 | n/a |
| move /mv → /home/u000000/mv (10,001 rows, open → private) | one `path` range UPDATE | 1 | 10,001 | 34 | all take the destination label |
| label lookup for one new row (nearest boundary of a 6-deep path) | `path IN (ancestors)` on the domain table | 1 | 1 | 0.24 (cold 0.6) | (1105, 2) |

Total wall time 43s.
