# tier: language
# world: none
n=0
until [ "$n" -ge 2 ]; do n=$((n+1)); echo "n=$n"; done > u.txt
mapfile -t lines < u.txt
echo "${lines[*]}"
