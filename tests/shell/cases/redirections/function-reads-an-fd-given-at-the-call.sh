# tier: language
# world: none
f() { read -r line <&3; echo "got $line"; }
echo through-three > f3
f 3< f3
