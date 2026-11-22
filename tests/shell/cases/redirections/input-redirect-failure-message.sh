# tier: language
# world: none
read -r x 2> err.txt < missing.txt
echo "status=$?"
IFS= read -r msg < err.txt
echo "$msg"
