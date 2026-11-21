# tier: language
# world: none
(exit 3) | (exit 0) | (exit 5)
s=("${PIPESTATUS[@]}")
echo "count=${#s[@]} values=${s[*]}"
echo "middle=${s[1]}"
