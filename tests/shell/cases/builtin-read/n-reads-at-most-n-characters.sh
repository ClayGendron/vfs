# tier: language
# world: none
read -n 3 x <<< "abcdef"
echo "x=[$x]"
read -n 10 y <<< "ab"
echo "y=[$y]"
