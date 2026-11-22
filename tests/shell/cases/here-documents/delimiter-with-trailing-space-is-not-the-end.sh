# tier: language
# world: none
mapfile -t lines <<EOF
body
EOF 
EOF
echo "count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
