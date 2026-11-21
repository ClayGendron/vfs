# tier: language
# world: none
a=(a b c)
unset a
echo "count=${#a[@]} set=${a+yes}"
b=(x y)
unset 'b[@]'
echo "b count=${#b[@]}"
