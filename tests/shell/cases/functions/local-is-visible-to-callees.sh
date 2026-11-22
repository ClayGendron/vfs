# tier: language
# world: none
show() { echo "show sees x=$x"; }
f() { local x=from-f; show; }
x=global
f
show
