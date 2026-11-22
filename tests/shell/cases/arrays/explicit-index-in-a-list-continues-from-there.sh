# tier: language
# world: none
a=(a [5]=b c [2]=d e)
for i in "${!a[@]}"; do echo "$i=${a[$i]}"; done
