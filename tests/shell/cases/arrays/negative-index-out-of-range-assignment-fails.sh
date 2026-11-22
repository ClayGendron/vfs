# tier: language
# world: none
a=(a b)
a[-3]=x
echo "status=$? values=${a[*]}"
