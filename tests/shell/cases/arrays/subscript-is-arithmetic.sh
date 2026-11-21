# tier: language
# world: none
a=(a b c d e)
i=1
echo "${a[i]} ${a[$i]} ${a[i+1]} ${a[2*2]} ${a[i<2?0:3]}"
