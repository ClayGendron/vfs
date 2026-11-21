# tier: language
# world: none
echo() { builtin echo "wrapped: $*"; }
echo hello world
unset -f echo
echo plain again
