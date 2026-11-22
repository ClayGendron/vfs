# tier: language
# world: none
declare -A m
m["one two"]=1
for k in "${!m[@]}"; do echo "quoted key: [$k]"; done
for k in ${!m[@]}; do echo "unquoted key: [$k]"; done
