# tier: language
# world: none
: > empty.txt
arr=(old values)
mapfile -t arr < empty.txt
echo "status=$? count=${#arr[@]}"
