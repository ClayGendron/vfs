# tier: language
# world: none
mapfile -t items <<< "$(printf 'a\n\n\n')"
echo "count=${#items[@]}"
