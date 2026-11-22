# tier: language
# world: none
x=$(echo a; exit 4; echo b)
echo "x=[$x] status=$?"
echo still running
