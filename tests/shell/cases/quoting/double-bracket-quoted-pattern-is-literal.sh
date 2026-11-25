# tier: language
# world: none
[[ abc == a* ]] && echo "unquoted glob matches"
[[ abc == "a*" ]] || echo "quoted glob does not match"
[[ 'a*' == "a*" ]] && echo "quoted matches literal star"
p='a*'
[[ abc == $p ]] && echo "unquoted variable is a pattern"
[[ abc == "$p" ]] || echo "quoted variable is literal"
