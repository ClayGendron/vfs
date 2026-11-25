# tier: program
# world: seed
printf 'x\ny\n' | tee a.txt b.txt > /dev/null
cat a.txt b.txt
