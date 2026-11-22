# tier: language
# world: none
f() { echo hi; }
type -t f
type -t echo
type -t nosuch_thing
echo "missing status=$?"
