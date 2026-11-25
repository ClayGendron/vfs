# tier: language
# world: none
declare -r x=1
declare x=2 2>/dev/null
echo "status=$? x=$x"
declare -r x=3 2>/dev/null
echo "status=$? x=$x"
