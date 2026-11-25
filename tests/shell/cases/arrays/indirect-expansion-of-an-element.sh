# tier: language
# world: none
a=(zero one two)
ref='a[2]'
echo "${!ref}"
ref='a[@]'
printf '[%s]' "${!ref}"; echo
