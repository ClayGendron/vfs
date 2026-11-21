# tier: language
# world: none
declare -ra fixed=(a b)
fixed[0]=z
echo "status=$? values=${fixed[*]}"
