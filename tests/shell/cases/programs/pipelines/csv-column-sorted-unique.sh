# tier: program
# world: seed
tail -n +2 data/people.csv | cut -d, -f3 | sort
