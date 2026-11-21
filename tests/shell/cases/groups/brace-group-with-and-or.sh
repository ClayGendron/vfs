# tier: language
# world: none
false || { echo a; echo b; }
true || { echo never; echo never; }
echo "done"
