# tier: language
# world: none
t=value
declare -n r=t
unset -n r
echo "t=$t r=[${r-unset}]"
