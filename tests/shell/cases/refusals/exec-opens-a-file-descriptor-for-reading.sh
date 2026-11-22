# tier: language
# world: none
printf 'first\nsecond\n' >input.txt
exec 3<input.txt
read -r a <&3
read -r -u 3 b
exec 3<&-
echo "a=$a b=$b"
