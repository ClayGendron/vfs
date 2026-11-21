# tier: language
# world: none
f() { echo "partial"; exit 9; echo "rest"; }
x=$(f)
echo "status=$? x=[$x]"
