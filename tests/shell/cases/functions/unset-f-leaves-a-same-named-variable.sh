# tier: language
# world: none
f=value
f() { echo "function"; }
unset -f f
echo "var=$f"
f 2>/dev/null
echo "status=$?"
