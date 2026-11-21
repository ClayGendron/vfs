# tier: language
# world: none
v=$'one\ntwo'
mapfile -t lines <<EOF
$v
EOF
echo "count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
