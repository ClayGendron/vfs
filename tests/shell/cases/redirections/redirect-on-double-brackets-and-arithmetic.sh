# tier: language
# world: none
[[ -n x ]] > a.txt
echo "status=$?"
(( 1 + 1 )) > b.txt
echo "status=$?"
mapfile -t a < a.txt; mapfile -t b < b.txt
echo "a lines=${#a[@]} b lines=${#b[@]}"
