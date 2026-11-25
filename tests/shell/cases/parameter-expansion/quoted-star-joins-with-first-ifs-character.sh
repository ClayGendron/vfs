# tier: language
# world: none
set -- a b c
IFS=':;'
echo "$*"
printf '[%s]\n' "$*"
