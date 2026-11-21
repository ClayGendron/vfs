# tier: language
# world: none
v='a b'
[[ $v == 'a b' ]] && echo "double bracket sees one word"
[[ -n $e ]] || echo "unquoted empty is still an operand"
