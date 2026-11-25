# tier: language
# world: none
echo() { builtin echo "wrapped: $*"; }
type -t echo
type -t -f echo 2>/dev/null || builtin echo "type -f status=$?"
