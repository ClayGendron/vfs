# tier: language
# world: none
read -n 5 x <<< $'ab\ncd'
echo "status=$? x=[$x]"
