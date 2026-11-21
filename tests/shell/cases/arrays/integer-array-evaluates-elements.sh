# tier: language
# world: none
declare -ai n=(1+1 "2*3")
n+=(10/2)
n[5]=7-1
echo "${n[*]}"
