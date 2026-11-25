# tier: language
# world: none
declare -A m
m[1+1]=expr
m[2]=two
echo "1+1=[${m[1+1]}] 2=[${m[2]}] count=${#m[@]}"
