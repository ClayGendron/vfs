# tier: language
# world: none
v=STOP
mapfile -t lines <<$v
body
STOP
$v
echo "count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
