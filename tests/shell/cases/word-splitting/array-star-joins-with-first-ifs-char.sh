# tier: language
# world: none
a=(x 'y z' w)
IFS=,
echo "${a[*]}"
IFS=
echo "${a[*]}"
unset IFS
echo "${a[*]}"
