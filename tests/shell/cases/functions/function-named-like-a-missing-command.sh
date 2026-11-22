# tier: language
# world: none
nosuchcommand
echo "before: $?"
nosuchcommand() { echo "now defined, args: $*"; }
nosuchcommand a b
echo "after: $?"
