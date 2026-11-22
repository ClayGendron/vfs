# tier: language
# world: none
f() { :; }
type -t f
unset -f f
type -t f
echo "status=$?"
