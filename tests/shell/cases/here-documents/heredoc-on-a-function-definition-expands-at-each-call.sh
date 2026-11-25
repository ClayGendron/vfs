# tier: language
# world: none
f() { IFS= read -r l; echo "got [$l]"; } <<EOF
value is $v
EOF
v=1; f
v=2; f
