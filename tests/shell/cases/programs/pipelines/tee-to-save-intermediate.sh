# tier: program
# world: seed
grep INFO logs/app.log | tee info.txt | wc -l
head -n 1 info.txt
