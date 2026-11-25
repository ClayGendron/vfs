# tier: language
# world: none
f() { echo "call $1"; } >> fdef.txt
f 1
f 2
mapfile -t lines < fdef.txt
printf '[%s]\n' "${lines[@]}"
