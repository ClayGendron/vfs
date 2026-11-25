# tier: program
# world: seed
printf 'a.b\naxb\n' | grep -F 'a.b'
echo ---
printf 'a.b\naxb\n' | grep 'a.b'
