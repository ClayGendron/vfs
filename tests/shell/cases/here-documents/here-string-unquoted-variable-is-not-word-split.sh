# tier: language
# world: none
v="a   b    c"
IFS= read -r x <<< $v
echo "x=[$x]"
