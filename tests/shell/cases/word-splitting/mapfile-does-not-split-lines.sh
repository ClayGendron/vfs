# tier: language
# world: none
mapfile -t lines <<'EOF'
one two
  three
EOF
echo "count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
