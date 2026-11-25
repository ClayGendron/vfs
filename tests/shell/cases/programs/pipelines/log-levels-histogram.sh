# tier: program
# world: seed
cut -d' ' -f3 logs/app.log | sort | uniq -c | sort -rn
