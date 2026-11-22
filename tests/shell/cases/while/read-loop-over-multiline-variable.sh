# tier: language
# world: none
text=$'first\nsecond\nthird'
n=0
while IFS= read -r line; do n=$((n + 1)); echo "$n: $line"; done <<< "$text"
