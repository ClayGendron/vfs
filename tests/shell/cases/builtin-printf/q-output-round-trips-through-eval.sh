# tier: language
# world: none
orig=$'two words\nand \'quotes\' $x'
q=$(printf '%q' "$orig")
eval "back=$q"
[ "$back" = "$orig" ] && echo "round trip ok"
