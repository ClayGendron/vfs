# tier: language
# world: none
a=(a b c d)
unset 'a[1]'
echo "count=${#a[@]} indices=${!a[*]} values=${a[*]}"
a+=(e)
echo "after append: ${!a[*]}"
