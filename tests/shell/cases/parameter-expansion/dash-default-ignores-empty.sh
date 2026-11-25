# tier: language
# world: none
x=
echo "[${x-fallback}]"
unset x
echo "[${x-fallback}]"
