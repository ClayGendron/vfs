# tier: language
# world: none
name() { echo "computed"; }
x=$(name)
echo "x=[$x]"
y="prefix-$(name)-suffix"
echo "y=[$y]"
