# tier: language
# world: none
x=$' a b\tc '
echo "[${x//[[:space:]]/}]"
