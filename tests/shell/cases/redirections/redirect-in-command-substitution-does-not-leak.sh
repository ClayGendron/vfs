# tier: language
# world: none
r=$(echo inside > sub.txt; echo returned)
read -r x < sub.txt
echo "r=$r x=$x"
