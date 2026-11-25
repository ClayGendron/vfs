# tier: language
# world: none
mapfile -t arr < <(for i in 1 2 3; do echo "item $i"; done)
printf '[%s]\n' "${arr[@]}"
