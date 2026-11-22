# tier: language
# world: none
set -- 'a b' c
printf '[%s]\n' $*
echo ---
printf '[%s]\n' "$*"
