# tier: language
# world: none
arr=(old)
read -r -a arr < /dev/null
echo "status=$? count=${#arr[@]}"
