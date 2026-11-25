# tier: language
# world: none
printf 'line1\nline2\n' > f
read -r x 3< f <&3
echo "x=$x"
