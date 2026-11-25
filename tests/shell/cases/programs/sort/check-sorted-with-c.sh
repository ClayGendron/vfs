# tier: program
# world: seed
sort -c data/words.txt
echo "status=$?"
sort data/words.txt | sort -c
echo "status=$?"
