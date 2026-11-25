# tier: language
# world: none
v=$'a b\n"c" \'d\' $e'
q=$(printf '%q' "$v")
eval "w=$q"
[ "$v" = "$w" ] && echo "round trip ok"
