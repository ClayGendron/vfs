# tier: language
# world: none
a=(one)
a+=(two "three four")
a+=()
echo "count=${#a[@]}"
printf '[%s]\n' "${a[@]}"
