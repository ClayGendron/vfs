# tier: language
# world: none
HOME=/home/agent
while IFS= read -r line; do echo "$line"; done <<EOF
tilde: ~ and ~/x
EOF
