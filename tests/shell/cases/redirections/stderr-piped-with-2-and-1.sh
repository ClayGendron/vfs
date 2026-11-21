# tier: language
# world: none
{ echo out; echo err >&2; } 2>&1 | while IFS= read -r l; do echo "got: $l"; done
