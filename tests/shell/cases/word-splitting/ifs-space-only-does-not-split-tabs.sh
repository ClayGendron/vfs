# tier: language
# world: none
IFS=' '
v=$'a  b\tc'
for w in $v; do printf '%q\n' "$w"; done
