# tier: program
# world: seed
tail -n +2 data/people.csv | sort -t, -k1,1 | while IFS=, read -r name age city; do printf '%-8s|%s|%s\n' "$name" "$age" "$city"; done
