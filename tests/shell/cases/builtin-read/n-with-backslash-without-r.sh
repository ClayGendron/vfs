# tier: language
# world: none
read -n 3 x <<< 'a\bcd'
echo "x=[$x]"
read -rn 3 y <<< 'a\bcd'
echo "y=[$y]"
