# tier: language
# world: none
read -r -a words <<< "the quick  brown   fox"
echo "count=${#words[@]}"
printf '[%s]\n' "${words[@]}"
