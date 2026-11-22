# tier: program
# world: seed
printf 'abc\nABC\n123\na1\n' | grep '^[[:alpha:]]*$'
echo ---
printf 'abc\nABC\n123\na1\n' | grep '[[:digit:]]'
