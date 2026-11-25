# tier: language
# world: none
let 'a[2] = 7' 'a[0] = a[2] * 2'
echo "${a[0]} ${a[2]} n=${#a[@]}"
