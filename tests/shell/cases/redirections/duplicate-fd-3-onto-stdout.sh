# tier: language
# world: none
{ echo "to three" >&3; echo "to one"; } 3> three.txt > one.txt
read -r a < three.txt; read -r b < one.txt
echo "three=[$a] one=[$b]"
