# tier: language
# world: none
a=(a b c)
unset a
echo "count=${#a[@]} [${a[*]-unset}]"
b=(x y)
unset 'b[@]'
echo "b count=${#b[@]}"
