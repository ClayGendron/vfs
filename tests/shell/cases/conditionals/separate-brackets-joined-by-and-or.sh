# tier: language
# world: none
a=1 b=2
[ "$a" = 1 ] && [ "$b" = 2 ]; echo "&&: $?"
[ "$a" = 9 ] || [ "$b" = 2 ]; echo "||: $?"
