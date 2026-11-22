# tier: language
# world: none
set -- drop "a  b" " c"
shift
printf '[%s]\n' "$@"
