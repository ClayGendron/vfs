# tier: language
# world: none
f() { echo "to $out"; } > "$out"
out=first.txt; f
out=second.txt; f
read -r a < first.txt; read -r b < second.txt
echo "a=[$a] b=[$b]"
