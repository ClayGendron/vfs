# tier: program
# world: seed
printf 'a\tb\n' | sed 's/\t/<TAB>/'
echo 'a b' | sed 's/ /\t/' | cat -A
