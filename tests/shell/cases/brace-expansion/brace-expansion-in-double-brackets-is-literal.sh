# tier: language
# world: none
[[ a == {a,b} ]] && echo "expanded" || echo "not expanded"
[[ '{a,b}' == {a,b} ]] && echo "literal"
