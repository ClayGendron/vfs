# tier: language
# world: none
mapfile -t arr <<'EOF'
a

b

EOF
echo "count=${#arr[@]}"
printf '[%s]\n' "${arr[@]}"
