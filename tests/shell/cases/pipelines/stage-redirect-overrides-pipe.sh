# tier: language
# world: none
echo hi > out.txt | { read -r x; echo "x=[$x]"; }
read -r y < out.txt
echo "file=[$y]"
