# tier: language
# world: none
echo data > "$(echo generated).txt"
read -r x < generated.txt
echo "x=$x"
