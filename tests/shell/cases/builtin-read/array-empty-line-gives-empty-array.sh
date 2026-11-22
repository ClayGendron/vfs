# tier: language
# world: none
arr=(old)
read -a arr <<< ""
echo "status=$? count=${#arr[@]}"
