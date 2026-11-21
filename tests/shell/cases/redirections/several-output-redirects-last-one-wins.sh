# tier: language
# world: none
echo payload > a.txt > b.txt
mapfile -t a < a.txt
mapfile -t b < b.txt
echo "a has ${#a[@]} lines, b=[${b[0]}]"
