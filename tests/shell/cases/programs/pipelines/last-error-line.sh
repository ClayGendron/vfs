# tier: program
# world: seed
grep ERROR logs/app.log | tail -n 1 | cut -d' ' -f4-
