# tier: language
# world: none
f() { echo "body output"; } > def.txt
f > call.txt
IFS= read -r d < def.txt
echo "def.txt: [$d]"
c=""
IFS= read -r c < call.txt
echo "call.txt: [$c] status=$?"
