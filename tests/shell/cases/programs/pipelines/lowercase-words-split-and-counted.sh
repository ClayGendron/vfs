# tier: program
# world: seed
tr -cs '[:alpha:]' '\n' < docs/notes.txt | tr 'A-Z' 'a-z' | sort | uniq -c | sort -rn | head -n 3
