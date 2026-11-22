# tier: language
# world: none
read v <<'EOF'
a\tb\\c\ d
EOF
echo "[$v]"
read -r v <<'EOF'
a\tb\\c\ d
EOF
echo "[$v]"
