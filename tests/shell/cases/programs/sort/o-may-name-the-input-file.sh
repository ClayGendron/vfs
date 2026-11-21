# tier: program
# world: seed
cp data/numbers.txt n.txt
sort -n -o n.txt n.txt
tr '\n' ' ' < n.txt
echo
