# tier: language
# world: none
{ read -r a; read -r b; } <<EOF
first
second
EOF
echo "a=$a b=$b"
