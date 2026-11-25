# tier: language
# world: none
a=1 b=2
[ "$a" = 1 -a "$b" = 2 ]; echo "-a both: $?"
[ "$a" = 1 -a "$b" = 3 ]; echo "-a one: $?"
[ "$a" = 9 -o "$b" = 2 ]; echo "-o one: $?"
[ "$a" = 9 -o "$b" = 9 ]; echo "-o none: $?"
