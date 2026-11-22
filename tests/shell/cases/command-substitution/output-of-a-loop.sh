# tier: language
# world: none
x=$(for i in 1 2 3; do printf '%s-' "$i"; done)
echo "[$x]"
