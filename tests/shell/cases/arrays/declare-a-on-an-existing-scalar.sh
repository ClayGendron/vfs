# tier: language
# world: none
s=value
declare -a s
s[1]=more
echo "count=${#s[@]} values=${s[*]}"
