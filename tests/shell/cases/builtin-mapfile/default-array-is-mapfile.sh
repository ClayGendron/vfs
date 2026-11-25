# tier: language
# world: none
mapfile -t <<< $'first\nsecond'
echo "count=${#MAPFILE[@]} last=${MAPFILE[1]}"
