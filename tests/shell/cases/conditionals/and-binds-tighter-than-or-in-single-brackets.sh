# tier: language
# world: none
[ x -o "" -a "" ]; echo "x -o (empty -a empty): $?"
[ "" -a "" -o x ]; echo "(empty -a empty) -o x: $?"
