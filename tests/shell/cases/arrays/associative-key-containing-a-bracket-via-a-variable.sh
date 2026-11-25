# tier: language
# world: none
declare -A m
key='a]b'
m[$key]=bracket
echo "value=${m[$key]} count=${#m[@]}"
for k in "${!m[@]}"; do echo "key=[$k]"; done
