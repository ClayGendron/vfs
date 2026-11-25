# tier: program
# world: seed
sed -n '/WARN/,/ERROR/p' logs/app.log
