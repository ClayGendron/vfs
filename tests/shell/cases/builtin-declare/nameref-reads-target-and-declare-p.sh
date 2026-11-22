# tier: language
# world: none
target=hi
declare -n r=target
echo "r=$r"
declare -p r
echo "name=${!r}"
