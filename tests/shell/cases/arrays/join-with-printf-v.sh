# tier: language
# world: none
a=(a b c)
printf -v joined '%s,' "${a[@]}"
joined=${joined%,}
echo "$joined"
