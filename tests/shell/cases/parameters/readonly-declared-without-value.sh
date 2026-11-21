# tier: language
# world: none
readonly ro
echo "[${ro-unset}]"
ro=x 2>/dev/null
echo "status=$?"
declare -r dr=fixed
echo "$dr"
