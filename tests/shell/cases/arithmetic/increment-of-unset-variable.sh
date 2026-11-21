# tier: language
# world: none
unset n
(( n++ ))
echo "n=$n"
unset m
echo "$((++m)) m=$m"
