# tier: language
# world: none
f=var
f() { echo "function f"; }
unset f
echo "after first unset: [${f-unset}]"
f
unset f
f 2>/dev/null
echo "after second unset: $?"
