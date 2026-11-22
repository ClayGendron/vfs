# tier: program
# world: seed
grep 'WARN\|ERROR' logs/app.log | wc -l
grep 'WARN|ERROR' logs/app.log
echo "status=$?"
