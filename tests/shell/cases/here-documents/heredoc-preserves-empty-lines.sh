# tier: language
# world: none
mapfile -t lines <<EOF
a

b

EOF
echo "count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
