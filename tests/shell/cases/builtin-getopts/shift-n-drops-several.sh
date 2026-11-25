# tier: language
# world: none
set -- a b c d e
shift 3
echo "count=$#"
printf '[%s]\n' "$@"
