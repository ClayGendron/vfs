# tier: language
# world: none
read v <<'EOF'
first \
second
EOF
echo "[$v]"
read -r v <<'EOF'
first \
second
EOF
echo "[$v]"
