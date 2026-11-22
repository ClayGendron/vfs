# tier: language
# world: none
set -- a b c d
echo "${@: -2}"
echo "${@: -1}"
