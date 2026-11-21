# tier: language
# world: none
echo invisible > /dev/null
echo "status=$?"
nosuchcommand 2>/dev/null
echo "status=$?"
{ echo a; echo b >&2; } &>/dev/null
echo "both gone status=$?"
