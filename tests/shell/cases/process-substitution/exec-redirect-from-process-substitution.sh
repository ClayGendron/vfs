# tier: language
# world: none
exec 3< <(printf 'first\nsecond\n')
read -r a <&3
read -r b <&3
exec 3<&-
echo "a=$a b=$b"
