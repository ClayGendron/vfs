# tier: language
# world: none
: <> created.txt
echo "status=$?"
mapfile -t lines < created.txt
echo "exists, lines=${#lines[@]}"
