# tier: language
# world: none
x=$(printf 'b\na\n' | while read -r l; do printf '%s,' "$l"; done)
echo "[$x]"
