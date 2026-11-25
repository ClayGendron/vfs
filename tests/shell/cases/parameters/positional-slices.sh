# tier: language
# world: none
set -- a b c d e
echo "${@:2}"
echo "${@:2:2}"
echo "${@: -1}"
echo "${*:0:1}"
