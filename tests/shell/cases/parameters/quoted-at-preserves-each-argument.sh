# tier: language
# world: none
set -- 'a b' c ''
echo "count=$#"
printf '[%s]\n' "$@"
