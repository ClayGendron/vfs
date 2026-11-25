# tier: language
# world: none
[[ "abc 123" =~ [[:digit:]]+ ]] && echo "digit: [${BASH_REMATCH[0]}]"
[[ "abc 123" =~ [[:space:]] ]] && echo "space found"
[[ "ABC" =~ ^[[:upper:]]+$ ]] && echo "all upper"
