# tier: language
# world: none
declare -a a
echo "count=${#a[@]} set=${a+yes}"
a[1]=x
declare -a b=(p q)
echo "a=${a[*]} b=${b[*]}"
