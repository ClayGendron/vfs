# tier: language
# world: none
n=3
echo three > "file$((n * 2))"
read -r x < file6
echo "x=$x"
