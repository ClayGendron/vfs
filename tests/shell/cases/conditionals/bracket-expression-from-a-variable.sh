# tier: language
# world: none
class='[0-9]'
[[ 7 == $class ]]; echo "7: $?"
[[ x == $class ]]; echo "x: $?"
[[ 5 == [![:alpha:]] ]]; echo "negated class: $?"
