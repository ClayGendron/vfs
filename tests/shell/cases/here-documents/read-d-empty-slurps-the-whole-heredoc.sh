# tier: language
# world: none
IFS= read -r -d '' text <<'EOF'
line one
  line two
EOF
echo "status=$?"
printf '[%s]\n' "$text"
