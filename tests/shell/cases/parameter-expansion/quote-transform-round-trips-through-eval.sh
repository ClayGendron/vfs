# tier: language
# world: none
x=$'mixed \'quotes\' and "more"\n$ \\'
eval "y=${x@Q}"
[ "$x" = "$y" ] && echo "round trip ok"
