# tier: language
# world: none
set --
echo "${1:-none} ${@:-empty} [${*-unset}]"
set -- ''
echo "[${1:-empty}] [${1-unset}]"
