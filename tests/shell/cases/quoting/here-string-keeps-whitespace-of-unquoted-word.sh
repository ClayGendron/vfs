# tier: language
# world: none
x='a   b'
read -r l <<< $x
echo "[$l]"
read -r l <<< "$x"
echo "[$l]"
