# tier: language
# world: none
a=('x y' '' z)
printf '[%s]\n' "${a[@]}"
echo ---
printf '[%s]\n' ${a[@]}
echo ---
printf '[%s]\n' "${a[*]}"
