# tier: language
# world: none
echo once > f
echo "after redirect" > g
echo "this goes to stdout"
read -r x < g
echo "g=$x"
