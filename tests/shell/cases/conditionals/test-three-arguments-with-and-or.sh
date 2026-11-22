# tier: language
# world: none
[ ! -a / ]; echo "bang-a: $?"
[ x -o "" ]; echo "x-o-empty: $?"
[ "" -a x ]; echo "empty-a-x: $?"
