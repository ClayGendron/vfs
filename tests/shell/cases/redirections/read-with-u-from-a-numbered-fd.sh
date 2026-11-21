# tier: language
# world: none
printf 'first\nsecond\n' > f
{ read -r -u 3 a; read -r -u 3 b; } 3< f
echo "a=$a b=$b"
