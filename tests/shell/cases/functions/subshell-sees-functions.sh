# tier: language
# world: none
f() { echo "f runs in subshell"; }
( f )
x=$(f)
echo "captured: $x"
