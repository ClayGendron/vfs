# tier: program
# world: seed
sed -nE 's/.*id=([0-9]+).*/\1/p' logs/app.log
