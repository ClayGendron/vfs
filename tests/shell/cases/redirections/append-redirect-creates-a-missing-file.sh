# tier: language
# world: none
echo created >> fresh.txt
echo "status=$?"
read -r x < fresh.txt
echo "x=$x"
