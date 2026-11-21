# tier: language
# world: none
echo "[${FUNCNAME[*]}] [${FUNCNAME-unset}]"
f() { echo "[$FUNCNAME]"; }
f
