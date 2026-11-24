tools=1107 servers=30 largest manifest=github/projects_write
| level | bytes | est. tokens | share of level 1 | times smaller |
| 1 full schemas | 577,934 | 140,303 | 100.00% | 1.0 |
| 1+ with annotations, outputSchema | 759,999 | 185,819 | 131.50% | 0.8 |
| 2 names only | 24,059 | 6,015 | 4.16% | 24.0 |
| 3 name + first sentence | 90,914 | 22,328 | 15.73% | 6.4 |
| 4a ls /.vfs/mcp | 412 | 103 | 0.07% | 1402.8 |
| 4b ls one server (median) | 212.0 | 53 | 0.04% | 2726.1 |
| 4b ls one server (max) | 7,853 | 1,964 | 1.36% | 73.6 |
| 4c every path | 58,482 | 14,621 | 10.12% | 9.9 |
| 5 one manifest, all tools (median) | 340 | 85 | 0.06% | 1699.8 |
| 5 one manifest, full-schema tools (median) | 612 | 153 | 0.11% | 944.3 |
| 5 one manifest (p90) | 1,610 | 403 | 0.28% | 359.0 |
| 5 one manifest (max) | 7,240 | 1,810 | 1.25% | 79.8 |
{
 "github": {
  "tools": 149,
  "name_bytes": 3025,
  "description_bytes": 21123,
  "input_schema_bytes": 124443,
  "of_which_property_descriptions": 52677,
  "output_schema_bytes": 162129
 },
 "alibaba-devops": {
  "tools": 203,
  "name_bytes": 4509,
  "description_bytes": 22039,
  "input_schema_bytes": 136569,
  "of_which_property_descriptions": 45882,
  "output_schema_bytes": 0
 }
}
multiplexed (a `method` enum): 20 ['actions_get', 'actions_list', 'actions_run_trigger', 'discussion_comment_write', 'issue_artifact_read', 'issue_artifact_write', 'issue_dependency_read', 'issue_dependency_write', 'issue_read', 'issue_write', 'label_write', 'projects_get', 'projects_list', 'projects_write', 'pull_request_artifact_read', 'pull_request_artifact_write', 'pull_request_read', 'pull_request_review_write', 'repository_ruleset_read', 'ui_get']
