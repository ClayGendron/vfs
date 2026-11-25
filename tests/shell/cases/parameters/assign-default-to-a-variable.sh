# tier: language
# world: none
unset v
echo "${v:=first}"
echo "${v:=second}"
v=
echo "[${v=kept}] [${v:=replaced}]"
