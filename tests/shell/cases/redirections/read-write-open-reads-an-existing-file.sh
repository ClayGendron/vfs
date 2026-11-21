# tier: language
# world: none
printf 'first\nsecond\n' > f
read -r x <> f
echo "x=$x"
