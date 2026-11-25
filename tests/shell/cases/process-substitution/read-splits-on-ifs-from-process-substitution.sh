# tier: language
# world: none
IFS=: read -r a b c < <(echo "x:y:z")
echo "a=$a b=$b c=$c"
