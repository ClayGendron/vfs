# tier: program
# world: seed
printf '' | tee empty-out.txt
echo "status=$?"
wc -c < empty-out.txt
