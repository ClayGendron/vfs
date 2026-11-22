# tier: program
# world: seed
echo 'hi' | tee t.txt | grep -c hi
echo "status=${PIPESTATUS[*]}"
