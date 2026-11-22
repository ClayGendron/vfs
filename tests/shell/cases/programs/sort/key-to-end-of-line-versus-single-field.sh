# tier: program
# world: seed
printf 'b 1 z\na 1 y\nc 0 x\n' | sort -k2
echo ---
printf 'b 1 z\na 1 y\nc 0 x\n' | sort -s -k2,2
