# tier: language
# world: none
v=$'line one\nline two'
for w in $v; do echo "[$w]"; done
echo ---
IFS=$'\n'
for w in $v; do echo "[$w]"; done
