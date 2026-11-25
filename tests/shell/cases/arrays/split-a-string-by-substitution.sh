# tier: language
# world: none
csv="red,green,blue"
a=(${csv//,/ })
echo "count=${#a[@]} second=${a[1]}"
