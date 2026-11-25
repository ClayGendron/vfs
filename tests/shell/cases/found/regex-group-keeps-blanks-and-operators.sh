# tier: language
# world: none
[[ "a  b" =~ (a  b) ]] && echo "1:${BASH_REMATCH[0]}"
[[ "< >" =~ (< >) ]] && echo "2:${BASH_REMATCH[1]}"
[[ "a b" =~ (a b|c) ]] && echo "3:ok"
[[ "ab" =~ (a)(b) ]] && echo "4:${BASH_REMATCH[2]}"
