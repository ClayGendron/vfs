# tier: language
# world: none
x="a b  c"
[[ $x == "a b  c" ]] && echo "unquoted left side kept whole"
y=
[[ $y == "" ]] && echo "empty left side needs no quotes"
[[ $never_set == "" ]] && echo "unset left side too"
