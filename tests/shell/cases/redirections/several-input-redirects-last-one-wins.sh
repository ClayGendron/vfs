# tier: language
# world: none
echo from-a > a.txt
echo from-b > b.txt
read -r x < a.txt < b.txt
echo "x=$x"
