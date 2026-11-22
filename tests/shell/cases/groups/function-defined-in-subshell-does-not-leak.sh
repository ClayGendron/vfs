# tier: language
# world: none
(inner() { :; }; declare -F inner >/dev/null && echo "defined inside")
declare -F inner >/dev/null || echo "not defined outside"
