# tier: language
# world: none
{ echo to-inner > inner.txt; echo to-outer; } > outer.txt
read -r a < inner.txt; read -r b < outer.txt
echo "inner=$a outer=$b"
