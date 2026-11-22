# tier: language
# world: none
IFS=
set -- 'a b' c ''
printf '[%s]\n' $*
echo ---
printf '[%s]\n' $@
