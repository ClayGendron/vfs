# tier: language
# world: none
x=ABC
declare -l x
echo "before=$x"
x=$x
echo "after=$x"
