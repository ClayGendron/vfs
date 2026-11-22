# tier: program
# world: seed
tail -n +2 data/people.csv | sort -t, -k2,2nr | head -n 1 | cut -d, -f1
