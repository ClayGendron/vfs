# tier: language
# world: none
for i in 1 2 3; do echo "line $i"; done > out.txt
mapfile -t got < out.txt
echo "${#got[@]} lines, last=[${got[2]}]"
