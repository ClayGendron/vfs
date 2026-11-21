# tier: language
# world: none
read -r a <<EOF | read -r b
unused
EOF
echo "status=$?"
