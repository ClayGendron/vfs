# tier: language
# world: none
(echo "from subshell") > sub.txt
read -r l < sub.txt
echo "l=[$l]"
