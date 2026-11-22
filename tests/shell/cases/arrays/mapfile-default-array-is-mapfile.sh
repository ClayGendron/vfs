# tier: language
# world: none
mapfile <<< $'one\ntwo'
echo "count=${#MAPFILE[@]} first=[${MAPFILE[0]%$'\n'}]"
