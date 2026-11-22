# tier: language
# world: none
a=("one two" three)
b=("${a[@]}")
b[0]=changed
echo "a: ${a[0]} | b: ${b[0]} count=${#b[@]}"
