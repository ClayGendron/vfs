# tier: program
# world: seed
uniq data/words.txt | wc -l
sort data/words.txt | uniq | wc -l
