# tier: language
# world: none
a=(x y z)
read -r 'a[1]' <<< "replaced value"
printf -v 'a[5]' '%s-%s' p q
for i in "${!a[@]}"; do echo "$i=[${a[i]}]"; done
