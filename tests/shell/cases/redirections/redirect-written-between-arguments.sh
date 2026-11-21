# tier: language
# world: none
echo one > mid.txt two three
read -r x < mid.txt
echo "x=[$x]"
