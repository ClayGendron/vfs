# tier: language
# world: none
{ echo "to stdout"; echo "to stderr" >&2; } 2>/dev/null
echo "status=$?"
