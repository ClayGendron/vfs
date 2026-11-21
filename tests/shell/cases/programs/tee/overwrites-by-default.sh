# tier: program
# world: seed
echo first > f.txt
echo second | tee f.txt > /dev/null
cat f.txt
