# tier: language
# world: none
arr=()
echo "[${arr[@]:-empty}]"
arr=(a b)
echo "[${arr[@]:-empty}]"
