# tier: language
# world: none
name=world
read -r greeting <<EOF
hello $name
EOF
echo "greeting=[$greeting]"
