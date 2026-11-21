# tier: language
# world: none
declare -ai a=(1+1 2*3 'a[0]+10')
printf '[%s]\n' "${a[@]}"
a+=(5-1)
echo "last=${a[3]}"
