# tier: language
# world: none
f() { echo body; } > def.txt
f > call.txt
mapfile -t d < def.txt; mapfile -t c < call.txt
echo "def=[${d[*]}] call lines=${#c[@]}"
