tools=1107 servers=30 origins={'toolsnap': 149, 'export': 203, 'docker-inputSchema': 143, 'docker-arguments': 310, 'docker-none': 302}

| server | tools | catalog bytes | est. tokens | bytes incl. annotations+outputSchema |
| zscaler-mcp-server | 302 | 34,725 | 8,682 | 34,725 |
| alibaba-devops | 203 | 172,142 | 38,899 | 172,142 |
| github | 149 | 155,201 | 38,795 | 335,860 |
| okta-mcp-server | 108 | 79,586 | 19,860 | 79,586 |
| maestro-mcp-server | 35 | 14,137 | 3,534 | 14,137 |
| keboola-mcp | 33 | 30,442 | 7,610 | 30,442 |
| kubectl-mcp-server | 26 | 5,013 | 1,254 | 5,013 |
| sonarqube | 25 | 9,407 | 2,352 | 9,407 |
| sqlite-mcp-server | 25 | 7,497 | 1,875 | 7,497 |
| stripe-remote | 25 | 3,245 | 812 | 3,245 |
| vectra-ai-rux-mcp-server | 25 | 12,456 | 3,114 | 12,456 |
| buildkite | 24 | 14,281 | 3,571 | 15,687 |

full-schema: tools=495 properties=2241
| row | properties | required | optional | share |
| string | 1471 | 970 | 501 | 65.6% |
| string-base64 | 0 | 0 | 0 | 0.0% |
| integer | 121 | 19 | 102 | 5.4% |
| number | 181 | 71 | 110 | 8.1% |
| boolean | 78 | 2 | 76 | 3.5% |
| enum | 173 | 52 | 121 | 7.7% |
| array-scalar | 63 | 6 | 57 | 2.8% |
| union-scalar | 91 | 89 | 2 | 4.1% |
| array-object | 16 | 7 | 9 | 0.7% |
| array-other | 6 | 2 | 4 | 0.3% |
| object-flat | 2 | 0 | 2 | 0.1% |
| object-nested | 7 | 5 | 2 | 0.3% |
| object-free | 28 | 13 | 15 | 1.2% |
| union | 4 | 0 | 4 | 0.2% |
| untyped | 0 | 0 | 0 | 0.0% |
  native_properties: 2087
  jsonvalued_properties: 154
  tools_zero_props: 7
  tools_native_only: 392
  tools_any_jsonvalued: 103
  tools_required_jsonvalued: 81
  tools_needing_json_fallback: 0
  tools_plain_words_only: 443
  wordish_properties: 91
  tools_rescued_by_dotted_flags: 1
  props_per_tool_median: 4
  props_per_tool_max: 33
  required_per_tool_median: 2
  positionals_median: 2
  camel_case_props: 887
  props_with_description: 2222

docker-arguments (lossy): tools=310 properties=556
| row | properties | required | optional | share |
| string | 406 | 368 | 38 | 73.0% |
| string-base64 | 0 | 0 | 0 | 0.0% |
| integer | 47 | 43 | 4 | 8.5% |
| number | 35 | 19 | 16 | 6.3% |
| boolean | 22 | 15 | 7 | 4.0% |
| enum | 0 | 0 | 0 | 0.0% |
| array-scalar | 11 | 2 | 9 | 2.0% |
| union-scalar | 0 | 0 | 0 | 0.0% |
| array-object | 6 | 4 | 2 | 1.1% |
| array-other | 18 | 18 | 0 | 3.2% |
| object-flat | 0 | 0 | 0 | 0.0% |
| object-nested | 0 | 0 | 0 | 0.0% |
| object-free | 11 | 7 | 4 | 2.0% |
| union | 0 | 0 | 0 | 0.0% |
| untyped | 0 | 0 | 0 | 0.0% |
  native_properties: 521
  jsonvalued_properties: 35
  tools_zero_props: 114
  tools_native_only: 284
  tools_any_jsonvalued: 26
  tools_required_jsonvalued: 25
  tools_needing_json_fallback: 0
  tools_plain_words_only: 284
  wordish_properties: 0
  tools_rescued_by_dotted_flags: 0
  props_per_tool_median: 1.0
  props_per_tool_max: 11
  required_per_tool_median: 1.0
  positionals_median: 1.0
  camel_case_props: 46
  props_with_description: 512

per server (full schema):
| server | tools | props | native | JSON-valued | tools native-only | tools plain words only | tools any JSON-valued | tools needing --json |
| alibaba-devops | 203 | 1041 | 926 | 115 | 133 | 184 | 70 | 0 |
| github | 149 | 817 | 799 | 18 | 136 | 136 | 13 | 0 |
| okta-mcp-server | 108 | 272 | 257 | 15 | 93 | 93 | 15 | 0 |
| vectra-ai-rux-mcp-server | 25 | 80 | 76 | 4 | 22 | 22 | 3 | 0 |
| alfresco | 10 | 31 | 29 | 2 | 8 | 8 | 2 | 0 |

annotations: {
 "github": {
  "tools": 149,
  "readOnlyHint=True": 69,
  "idempotentHint=False": 145,
  "title": 149,
  "readOnlyHint=False": 80,
  "destructiveHint=True": 20,
  "write_without_destructiveHint": 28,
  "destructiveHint=False": 34,
  "openWorldHint=True": 38,
  "idempotentHint=True": 3
 },
 "alibaba-devops": {
  "tools": 203,
  "write_without_destructiveHint": 203
 },
 "docker-registry": {
  "tools_with_annotations": 24,
  "readOnlyHint=True": 20
 }
}
description bytes: {'median': 58, 'p90': 216, 'max': 3050, 'empty': 0}
tools needing --json: 0
