# tier: program
# world: seed
printf 'a\nb\n' | sed -z 's/\n/,/g'
echo
