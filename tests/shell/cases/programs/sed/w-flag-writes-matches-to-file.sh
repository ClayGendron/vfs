# tier: program
# world: seed
sed -n 's/ERROR/E/w errors.txt' logs/app.log
cat errors.txt
