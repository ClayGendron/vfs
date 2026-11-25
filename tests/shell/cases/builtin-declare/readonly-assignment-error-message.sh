# tier: language
# world: none
readonly r=1
{ r=2; } 2>&1
echo "after status=$?"
