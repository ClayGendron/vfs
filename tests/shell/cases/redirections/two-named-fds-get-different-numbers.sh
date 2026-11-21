# tier: language
# world: none
: {a}> fa {b}> fb
[ "$a" != "$b" ] && echo "different"
echo A >&$a; echo B >&$b
: {a}>&- {b}>&-
read -r x < fa; read -r y < fb
echo "fa=$x fb=$y"
