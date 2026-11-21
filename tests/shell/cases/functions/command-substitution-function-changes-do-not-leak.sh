# tier: language
# world: none
counter=0
bump() { counter=$(( counter + 1 )); echo "$counter"; }
a=$(bump)
b=$(bump)
echo "a=$a b=$b counter=$counter"
bump > /dev/null
echo "direct counter=$counter"
