# tier: language
# world: none
read -a words <<< "red green blue"
echo "count=${#words[@]}"
printf '[%s]\n' "${words[@]}"
