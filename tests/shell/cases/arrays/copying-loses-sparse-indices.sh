# tier: language
# world: none
a=([3]=x [7]=y)
b=("${a[@]}")
echo "a indices: ${!a[*]}"
echo "b indices: ${!b[*]}"
