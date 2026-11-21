# tier: language
# world: none
echo() { printf 'function echo: %s\n' "$*"; }
echo one
builtin echo two
