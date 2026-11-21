# tier: language
# world: none
v="a b c"
q=("$v")
u=($v)
echo "quoted count=${#q[@]} unquoted count=${#u[@]}"
