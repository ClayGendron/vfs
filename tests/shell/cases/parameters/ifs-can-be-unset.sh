# tier: language
# world: none
unset IFS
echo "[${IFS-unset}]"
IFS=
echo "[${IFS-unset}] [${IFS+set}]"
