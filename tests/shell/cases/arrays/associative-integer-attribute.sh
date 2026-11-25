# tier: language
# world: none
declare -Ai count
count[a]=2+3
count[b]+=4
count[b]+=1
echo "a=${count[a]} b=${count[b]}"
