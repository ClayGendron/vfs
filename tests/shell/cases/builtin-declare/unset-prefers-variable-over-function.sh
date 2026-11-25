# tier: language
# world: none
f() { echo "function f"; }
f=variable
unset f
echo "var=[${f-unset}]"
f
unset f
f 2>/dev/null
echo "status=$?"
