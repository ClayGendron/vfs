# tier: language
# world: seed
arr=(old)
mapfile -t arr < empty.txt
echo "status=$? count=${#arr[@]}"
