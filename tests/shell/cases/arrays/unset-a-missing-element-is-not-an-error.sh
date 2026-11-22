# tier: language
# world: none
a=(a b)
unset 'a[5]'
echo "status=$? count=${#a[@]}"
