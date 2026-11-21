# tier: language
# world: none
v=value
f() { echo "f:$1"; }
while read -r l; do echo "[$l]"; done < <(echo "$v"; f arg)
