# tier: language
# world: none
x=""
[[ -n $x ]] && echo "has value" || echo "empty"
x=v
[[ -n $x ]] && echo "has value" || echo "empty"
