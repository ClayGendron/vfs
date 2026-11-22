# tier: language
# world: none
t=value
declare -n r=t
unset r
echo "t=[${t-unset}]"
declare -p r
