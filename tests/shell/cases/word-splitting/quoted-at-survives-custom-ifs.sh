# tier: language
# world: none
IFS=:
set -- 'a:b' 'c d'
printf '[%s]\n' "$@"
echo ---
printf '[%s]\n' $@
