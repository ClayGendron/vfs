# tier: language
# world: none
declare -A m
m[x]=1
m[y]=2
m[z]=3
for k in "${!m[@]}"; do echo "$k=${m[$k]}"; done
