# tier: language
# world: none
m[foo]=bar
m[baz]=qux
echo "count=${#m[@]} indices=${!m[*]} value=${m[foo]}"
