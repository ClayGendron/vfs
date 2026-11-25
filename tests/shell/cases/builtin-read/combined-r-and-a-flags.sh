# tier: language
# world: none
read -ra arr <<< 'a\b c\d'
printf '[%s]\n' "${arr[@]}"
