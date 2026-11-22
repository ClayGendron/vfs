# tier: language
# world: none
printf 'first\nsecond\n' > in.txt
take() { read -r a; read -r b; echo "a=$a b=$b"; } < in.txt
take
take
