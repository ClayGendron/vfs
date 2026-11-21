# tier: language
# world: none
name="my file.txt"
echo spaced > "$name"
read -r x < "my file.txt"
echo "x=$x"
