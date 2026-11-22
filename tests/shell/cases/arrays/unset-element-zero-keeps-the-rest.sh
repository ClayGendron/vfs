# tier: language
# world: none
a=(a b c)
unset 'a[0]'
echo "\$a=[${a-unset}] all=${a[*]}"
