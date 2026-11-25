# tier: language
# world: none
x=global
f() { local x; echo "x=[${x-unset}]"; x=assigned; echo "x=[$x]"; }
f
echo "global x=[$x]"
