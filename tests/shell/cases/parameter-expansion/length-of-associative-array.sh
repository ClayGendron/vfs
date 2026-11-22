# tier: language
# world: none
declare -A m=([k1]=v [k2]=vv [k3]=vvv)
echo "count=${#m[@]} k3=${#m[k3]}"
