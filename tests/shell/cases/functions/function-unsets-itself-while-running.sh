# tier: language
# world: none
f() { unset -f f; echo "still running"; }
f
f 2>/dev/null
echo "second call status=$?"
