# tier: language
# world: none
greet() { echo "hello $1"; echo "bye $1"; }
x=$(greet you)
printf '[%s]\n' "$x"
