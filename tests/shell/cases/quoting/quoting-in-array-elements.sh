# tier: language
# world: none
a=('x y' "z" w\ v '' $'t\tu')
echo "count=${#a[@]}"
printf '[%s]\n' "${a[@]}"
