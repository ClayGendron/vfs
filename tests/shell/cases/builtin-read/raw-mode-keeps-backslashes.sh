# tier: language
# world: none
read -r x <<< 'a\b\\c'
echo "x=[$x]"
read -r y <<< 'C:\temp\new'
echo "y=[$y]"
