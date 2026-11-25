# tier: program
# world: seed
printf 'x\nx\ny\n' | sed -n '0,/x/p'
echo ---
printf 'x\nx\ny\n' | sed -n '1,/x/p'
