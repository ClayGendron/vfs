# tier: language
# world: none
declare -A m
m[first]="value one"
m[second]="value two"
for v in "${m[@]}"; do echo "[$v]"; done
