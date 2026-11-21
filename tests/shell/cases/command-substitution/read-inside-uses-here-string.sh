# tier: language
# world: none
x=$(read -r a b <<< "1 2"; echo "$b$a")
echo "[$x]"
