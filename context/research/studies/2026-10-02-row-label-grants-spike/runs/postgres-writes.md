## postgres — writes: 1,000-user world plus /mid (1,000 rows), /mv (10,000), /big (200,000); 234,116 entries

| operation | statement shape | statements | rows touched | total ms (median of runs) | labels after |
|---|---|---|---|---|---|
| posture /mid → shared (1,000 rows) | 1 points + 1 open ranges (0 deeper postures cut); range join, <=500 pieces/statement | 2 | 1,001 | 27 | all correct |
| posture /mid → shared, chunked | 1 points + 1 open ranges (0 deeper postures cut); keyset chunks of 500 rows | 7 | 1,001 | 16 | all correct |
| posture /big → shared (200,000 rows) | 1 points + 1 open ranges (0 deeper postures cut); range join, <=500 pieces/statement | 2 | 200,001 | 1,895 | all correct |
| posture /big → shared, chunked | 1 points + 1 open ranges (0 deeper postures cut); keyset chunks of 50,000 rows | 11 | 200,001 | 1,865 | all correct |
| posture /big → shared, chunked | 1 points + 1 open ranges (0 deeper postures cut); keyset chunks of 200,000 rows | 5 | 200,001 | 1,898 | all correct |
| posture / → shared (root minus every deeper posture) | 1103 points + 2205 open ranges (1,102 deeper postures cut); range join, <=500 pieces/statement | 8 | 12,014 | 305 | all correct |
| posture / → shared, chunked | 1103 points + 2205 open ranges (1,102 deeper postures cut); keyset chunks of 50,000 rows | 4,413 | 12,014 | 2,832 | all correct |
| domain variant: posture /mid (1,000 rows) | `domain_id = :d` | 1 | 1,001 | 39 | all correct |
| domain variant: posture /big (200,000 rows) | `domain_id = :d` | 1 | 200,001 | 2,151 | all correct |
| grant at a new prefix over /big: public_level variant | no row write | 0 | 0 | 0 | n/a |
| grant at a new prefix over /big: domain variant | `path` range | 1 | 200,000 | 2,271 | n/a |
| move /mv → /home/u000000/mv (10,001 rows, open → private) | one `path` range UPDATE | 1 | 10,001 | 87 | all take the destination label |
| label lookup for one new row (nearest boundary of a 6-deep path) | `path IN (ancestors)` on the domain table | 1 | 1 | 1.27 (cold 3.3) | (1105, 2) |

Total wall time 64s.
