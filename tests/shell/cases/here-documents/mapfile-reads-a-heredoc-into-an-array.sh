# tier: language
# world: none
mapfile -t items <<EOF
apple
banana split
cherry
EOF
echo "count=${#items[@]}"
printf '[%s]\n' "${items[@]}"
