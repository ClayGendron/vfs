# tier: program
# world: seed
cut -d, -f2- data/people.csv | head -n 2
cut -d, -f-2 data/people.csv | head -n 2
