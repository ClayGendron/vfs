# tier: language
# world: none
f() { export Z=set-in-f; }
f
echo "Z=$Z"
declare -p Z
