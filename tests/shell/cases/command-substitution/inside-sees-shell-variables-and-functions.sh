# tier: language
# world: none
v=outer
g() { echo "g:$1"; }
echo "$(echo "$v"; g arg)"
