# tier: language
# world: none
declare -A m=([one]=1 [two]=2)
echo $(( m[one] + m[two] ))
