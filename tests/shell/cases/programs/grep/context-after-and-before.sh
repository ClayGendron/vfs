# tier: program
# world: seed
grep -A1 WARN logs/app.log
echo ---
grep -B1 stop logs/app.log
