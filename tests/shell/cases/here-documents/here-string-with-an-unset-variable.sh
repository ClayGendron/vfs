# tier: language
# world: none
unset nothing
mapfile -t items <<< $nothing
echo "count=${#items[@]} first=[${items[0]}]"
