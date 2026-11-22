# tier: language
# world: none
set --
printf '[%s]\n' "$*"
set -- "$*"
echo "count=$#"
