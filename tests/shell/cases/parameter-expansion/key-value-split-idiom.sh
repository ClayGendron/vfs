# tier: language
# world: none
line='name=value=with=equals'
echo "key=${line%%=*}"
echo "val=${line#*=}"
