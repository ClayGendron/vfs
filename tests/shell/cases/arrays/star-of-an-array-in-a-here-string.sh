# tier: language
# world: none
a=(x y z)
read -r first rest <<< "${a[*]}"
echo "first=$first rest=$rest"
