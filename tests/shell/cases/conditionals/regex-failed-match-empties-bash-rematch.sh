# tier: language
# world: none
[[ abc =~ (b) ]]
echo "after match: [${BASH_REMATCH[1]}] count=${#BASH_REMATCH[@]}"
[[ abc =~ (z) ]]
echo "after failure: count=${#BASH_REMATCH[@]}"
