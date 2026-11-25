# tier: language
# world: none
text=$'first line\nsecond line'
read -r x <<< "$text"
echo "x=[$x]"
