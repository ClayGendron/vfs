# tier: language
# world: none
echo a2>f1
echo b 2>f2
echo 2 >f3
read -r x < f1; echo "f1=[$x]"
mapfile -t y < f2; echo "f2 lines=${#y[@]}"
read -r z < f3; echo "f3=[$z]"
