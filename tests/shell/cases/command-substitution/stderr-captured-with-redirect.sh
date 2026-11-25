# tier: language
# world: none
y=$( { echo out; echo err >&2; } 2>&1 )
printf 'y=[%s]\n' "$y"
