# tier: language
# world: none
while IFS= read -r line; do echo "[$line]"; done <<'EOF'
dollar: \$v
continued \
not joined
EOF
