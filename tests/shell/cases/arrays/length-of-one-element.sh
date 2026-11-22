# tier: language
# world: none
a=(short "a longer one" "")
echo "0:${#a[0]} 1:${#a[1]} 2:${#a[2]}"
echo "plain \${#a} = ${#a}"
