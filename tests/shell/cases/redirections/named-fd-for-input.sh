# tier: language
# world: none
printf 'one\ntwo\n' > f
: {in}< f
read -r -u "$in" a
read -r -u "$in" b
: {in}<&-
echo "a=$a b=$b"
