# tier: language
# world: none
read -r x < missing.txt
echo "status=$?"
echo "x=[${x-unset}]"
