# tier: program
# world: seed
head -n 3 logs/app.log | tail -n 1
tail -n +2 data/people.csv | head -n 2
