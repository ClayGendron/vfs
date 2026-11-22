# tier: language
# world: none
mapfile -t lines <<'EOF'
alpha
beta gamma
delta
EOF
echo "count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
