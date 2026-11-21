# tier: language
# world: none
[[ a == a || b == c && d == e ]]; echo "a||(b&&d): $?"
[[ ( a == a || b == c ) && d == e ]]; echo "(a||b)&&d: $?"
