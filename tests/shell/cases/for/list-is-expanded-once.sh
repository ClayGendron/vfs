# tier: language
# world: none
list="a b"
for x in $list; do list="z"; echo "x=$x"; done
echo "list=$list"
