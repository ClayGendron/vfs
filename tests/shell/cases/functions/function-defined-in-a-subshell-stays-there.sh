# tier: language
# world: none
( f() { echo "in subshell"; }; f )
f 2>/dev/null
echo "outside status=$?"
