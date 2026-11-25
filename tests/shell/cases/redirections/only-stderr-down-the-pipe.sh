# tier: language
# world: none
{ echo out; echo err >&2; } 2>&1 >/dev/null | while IFS= read -r l; do echo "got: $l"; done
