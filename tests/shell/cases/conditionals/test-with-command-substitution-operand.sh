# tier: language
# world: none
[[ $(printf 'abc') == abc ]]; echo "substitution: $?"
[ -z "$(printf '')" ]; echo "empty substitution: $?"
