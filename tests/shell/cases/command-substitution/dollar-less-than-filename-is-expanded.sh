# tier: language
# world: none
echo content > data.txt
name=data
x=$(<"$name.txt")
echo "[$x]"
