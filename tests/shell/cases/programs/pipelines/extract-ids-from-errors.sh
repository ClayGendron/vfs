# tier: program
# world: seed
grep ERROR logs/app.log | sed -E 's/.*id=([0-9]+).*/\1/' | tr '\n' ','
echo
