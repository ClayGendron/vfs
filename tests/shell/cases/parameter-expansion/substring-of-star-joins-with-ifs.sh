# tier: language
# world: none
set -- a b c d
IFS=,
echo "${*:2}"
echo "${*:1:2}"
