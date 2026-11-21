# tier: language
# world: none
echo hi > nodir/out | echo "second stage runs"
echo "status=$?"
echo hi | read -r x < missing.txt
echo "status=$?"
