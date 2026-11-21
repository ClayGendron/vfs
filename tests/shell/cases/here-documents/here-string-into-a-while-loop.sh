# tier: language
# world: none
n=0
while read -r w; do n=$((n+1)); echo "$n=$w"; done <<< $'x\ny'
echo "n=$n"
