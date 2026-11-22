# tier: program
# world: seed
grep -q ERROR logs/app.log
echo "status=$?"
grep -q FATAL logs/app.log
echo "status=$?"
