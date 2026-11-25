# tier: language
# world: none
v=parent
f() { echo "f sees $v"; }
(f; echo "subshell sees v=$v")
