# tier: language
# world: none
set -- a "b c" d
echo "count=$#"
printf '[%s]\n' "$@"
