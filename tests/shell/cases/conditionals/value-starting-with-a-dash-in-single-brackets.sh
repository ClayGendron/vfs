# tier: language
# world: none
x=-n
[ "$x" = -n ]; echo "x is -n: $?"
x='!'
[ "$x" = '!' ]; echo "x is !: $?"
x='('
[ "$x" = '(' ]; echo "x is (: $?"
