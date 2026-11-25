# tier: language
# world: none
x=$(f() { echo hi; }; f)
echo "x=[$x]"
f 2>/dev/null
echo "status: $?"
