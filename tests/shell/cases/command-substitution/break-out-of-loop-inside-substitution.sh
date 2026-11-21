# tier: language
# world: none
x=$(for i in 1 2 3; do echo "$i"; [ "$i" = 2 ] && break; done)
printf '[%s]\n' "$x"
