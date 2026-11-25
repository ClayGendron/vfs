# tier: language
# world: none
a=($'line one\nline two' after)
echo "count=${#a[@]}"
printf '<%s>\n' "${a[0]}"
