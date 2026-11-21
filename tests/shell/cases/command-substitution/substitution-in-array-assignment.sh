# tier: language
# world: none
arr=( $(echo 'a b  c') )
echo "n=${#arr[@]} second=${arr[1]}"
q=( "$(echo 'a b  c')" )
echo "n=${#q[@]}"
