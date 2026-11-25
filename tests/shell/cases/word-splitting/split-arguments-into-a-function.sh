# tier: language
# world: none
f() { echo "count=$#"; }
v='a b c'
f $v
f "$v"
f ${v}x
