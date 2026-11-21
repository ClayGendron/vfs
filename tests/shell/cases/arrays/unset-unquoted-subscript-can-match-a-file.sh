# tier: language
# world: none
: > a0
a=(x y)
a0=variable
unset a[0]
echo "count=${#a[@]} a0=[${a0-unset}]"
unset 'a[0]'
echo "count=${#a[@]}"
