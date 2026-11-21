# tier: program
# world: seed
sort data/words.txt | tee sorted.txt | uniq -c | head -n 2
wc -l < sorted.txt
