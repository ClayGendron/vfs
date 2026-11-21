# tier: language
# world: none
prefix() { while IFS= read -r l; do echo "f:$l"; done; }
printf '%s\n' a b | prefix
