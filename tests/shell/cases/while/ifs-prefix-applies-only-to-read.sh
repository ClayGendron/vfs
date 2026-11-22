# tier: language
# world: none
IFS=: read -r a b <<< "1:2"
echo "a=$a b=$b"
v="p q"
for w in $v; do printf '[%s]' "$w"; done
echo
