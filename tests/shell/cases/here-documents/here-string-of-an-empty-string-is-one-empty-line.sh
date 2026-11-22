# tier: language
# world: none
mapfile -t items <<< ""
echo "count=${#items[@]} first=[${items[0]}]"
read -r x <<< ""
echo "read status=$?"
