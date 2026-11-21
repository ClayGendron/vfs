# tier: language
# world: none
a=([2]=x [4]=y [7]=z)
IFS=:
echo "${!a[*]}"
printf '[%s]' "${!a[@]}"; echo
