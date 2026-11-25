# tier: language
# world: none
set_it() { x=set-by-callee; }
f() { local x=original; set_it; echo "in f: $x"; }
x=global
f
echo "global: $x"
