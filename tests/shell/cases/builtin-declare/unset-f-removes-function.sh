# tier: language
# world: none
f() { echo "function f"; }
f=variable
unset -f f
echo "var=$f"
f 2>/dev/null
echo "status=$?"
