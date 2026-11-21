# tier: language
# world: none
set -- -x -e --
echo "count=$#"
printf '[%s]\n' "$@"
[[ -o xtrace ]] || echo "xtrace stays off"
