# tier: language
# world: none
a=1 b=$a c=$b$a
echo "b=$b c=$c"
a=2 a=$a$a
echo "a=$a"
