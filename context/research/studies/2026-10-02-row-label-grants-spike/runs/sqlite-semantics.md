## Semantics on SQLite — a 1,000-user world, then `shared` at `/home/u000001/pub` and `/mv` moved into `/home/u000002`

| caller | variant | visible | matches truth | `/home/u000001/pub` | `/home/u000001/pub/p0.md` | `/home/u000001` | `/home/u000001/f000.md` | `/home/u000001-x` | `/home/u000002/mv/m0.md` | `/home/u000002/f000.md` |
|---|---|---|---|---|---|---|---|---|---|---|
| anonymous | public | 2,019 | exact | yes | yes | no | no | no | no | no |
| anonymous | domain | 2,019 | exact | yes | yes | no | no | no | no | no |
| u000001 (owns the home with the nested shared folder) | public | 2,040 | exact | yes | yes | yes | yes | no | no | no |
| u000001 (owns the home with the nested shared folder) | domain | 2,040 | exact | yes | yes | yes | yes | no | no | no |
| u000002 (owns the home the subtree moved into) | public | 2,051 | exact | yes | yes | no | no | no | yes | yes |
| u000002 (owns the home the subtree moved into) | domain | 2,051 | exact | yes | yes | no | no | no | yes | yes |
| u000005 (owned the moved rows; no grant on the destination) | public | 2,050 | exact | yes | yes | no | no | no | yes | no |
| u000005 (owned the moved rows; no grant on the destination) | domain | 2,050 | exact | yes | yes | no | no | no | yes | no |
| u000003 (a bystander) | public | 2,040 | exact | yes | yes | no | no | no | no | no |
| u000003 (a bystander) | domain | 2,040 | exact | yes | yes | no | no | no | no | no |

Reading the columns: the nested shared folder is visible to everyone while the rest of the home stays hidden; the owner sees all of it through the grant; the sibling trap `/home/u000001-x` is visible to nobody; the moved rows are visible to the destination's owner through the grant and hidden from everyone else — except their former owner, who still sees them through the owner floor (`owner_id = me` is mount-wide in the spec's rules and in the shipped single-subject owner arm). The truth function and both variants agree on that; whether a move into another user's private home should keep the mover's floor is a question for the spec.
