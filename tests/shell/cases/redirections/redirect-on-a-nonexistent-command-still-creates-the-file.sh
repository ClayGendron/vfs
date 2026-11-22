# tier: language
# world: none
nosuchcommand > created.txt 2>/dev/null
echo "status=$?"
mapfile -t lines < created.txt
echo "file exists, lines=${#lines[@]}"
