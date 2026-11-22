# tier: program
# world: seed
while read -r a; do echo "only-in-sorted: $a"; done < <(sort -u data/words.txt | head -n 2)
