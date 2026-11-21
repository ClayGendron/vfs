# tier: language
# world: none
counter=0
bump() { counter=$((counter + 1)); }
bump
bump
echo "counter=$counter"
