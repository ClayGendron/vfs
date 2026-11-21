# tier: language
# world: none
a=(a b c d)
IFS=,
echo "${a[*]:1:2}"
printf '[%s]\n' "${a[*]:1:2}"
