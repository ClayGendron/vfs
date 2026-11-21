# tier: language
# world: none
command echo via-command > c.txt
read -r x < c.txt
echo "x=$x"
