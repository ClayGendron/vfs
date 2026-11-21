# tier: program
# world: seed
sed 's/[0-9]//g' logs/app.log | cut -d' ' -f3 | sort -u
