# tier: language
# world: none
read -r x < /dev/null
echo "status=$? x=[$x]"
mapfile -t arr < /dev/null
echo "elements=${#arr[@]}"
