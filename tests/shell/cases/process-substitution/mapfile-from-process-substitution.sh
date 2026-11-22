# tier: language
# world: none
mapfile -t lines < <(printf 'p\nq\nr\n')
echo "n=${#lines[@]} first=${lines[0]} last=${lines[2]}"
