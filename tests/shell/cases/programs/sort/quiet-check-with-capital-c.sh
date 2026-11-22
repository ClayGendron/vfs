# tier: program
# world: seed
sort -C data/numbers.txt
echo "status=$?"
sort -n data/numbers.txt | sort -nC
echo "status=$?"
