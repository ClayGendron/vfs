# tier: language
# world: none
IFS=: read -r a b <<< "1:2"
echo "a=$a b=$b"
printf '%q\n' "$IFS"
