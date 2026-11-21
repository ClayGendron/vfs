# tier: language
# world: none
declare -A m
for k in alpha beta gamma delta epsilon; do m[$k]=${#k}; done
echo "keys: ${!m[*]}"
echo "values: ${m[*]}"
