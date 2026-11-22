# tier: language
# world: none
printf 'first\nsecond\n' > f
read -r a < f
read -r b < f
echo "a=$a b=$b"
