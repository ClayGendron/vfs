# tier: language
# world: none
echo "echo ignores stdin" <<EOF
body not printed
EOF
echo "status=$?"
