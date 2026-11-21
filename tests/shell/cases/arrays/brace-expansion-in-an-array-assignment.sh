# tier: language
# world: none
a=({1..5})
b=(file{A,B}.txt)
echo "a=${a[*]} count=${#a[@]}"
echo "b=${b[*]}"
