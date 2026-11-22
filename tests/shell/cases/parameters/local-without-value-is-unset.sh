# tier: language
# world: none
x=top
f() { local x; echo "[${x-unset}]"; x=set; echo "[$x]"; }
f
echo "after: $x"
