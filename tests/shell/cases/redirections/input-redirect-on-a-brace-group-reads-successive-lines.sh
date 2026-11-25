# tier: language
# world: none
printf 'first\nsecond\nthird\n' > f
{ read -r a; read -r b; } < f
echo "a=$a b=$b"
