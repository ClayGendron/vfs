# tier: language
# world: none
echo data > "$(echo out).txt"
read -r l < out.txt
echo "[$l]"
