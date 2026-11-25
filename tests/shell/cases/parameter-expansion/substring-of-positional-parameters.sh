# tier: language
# world: none
set -- a b c d e
printf '[%s]\n' "${@:2:2}"
echo "${@:4}"
