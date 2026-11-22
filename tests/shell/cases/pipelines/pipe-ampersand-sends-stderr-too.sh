# tier: language
# world: none
{ echo out; echo err >&2; } |& while IFS= read -r l; do echo "got:$l"; done
