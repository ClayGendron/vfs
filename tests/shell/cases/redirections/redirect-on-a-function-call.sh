# tier: language
# world: none
f() { echo "from f"; }
f > call.txt
read -r x < call.txt
echo "x=$x"
