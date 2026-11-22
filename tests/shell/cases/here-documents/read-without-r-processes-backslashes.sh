# tier: language
# world: none
read x <<'EOF'
a\b\\c
EOF
read -r y <<'EOF'
a\b\\c
EOF
echo "without-r=[$x] with-r=[$y]"
