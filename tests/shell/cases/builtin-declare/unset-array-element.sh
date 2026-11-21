# tier: language
# world: none
a=(a b c)
unset 'a[1]'
echo "count=${#a[@]} indices=${!a[*]} values=${a[*]}"
