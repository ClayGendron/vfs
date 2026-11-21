# tier: language
# world: none
x="a b"
y='c d'
z=e\ f
w=$'g\th'
printf '[%s]\n' "$x" "$y" "$z" "$w"
