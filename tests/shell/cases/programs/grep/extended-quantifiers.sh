# tier: program
# world: seed
printf 'ac\nabc\nabbc\n' | grep -E 'ab+c'
echo ---
printf 'ac\nabc\nabbc\n' | grep -E 'ab?c'
echo ---
printf 'ac\nabc\nabbc\n' | grep -E 'ab{2}c'
