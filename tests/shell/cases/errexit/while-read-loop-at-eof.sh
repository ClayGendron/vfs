# tier: language
# world: none
set -e
while read -r line; do echo "got $line"; done <<'EOF'
a
b
EOF
echo "loop done"
