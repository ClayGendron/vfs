# tier: language
# world: none
a=(a b c)
IFS=
echo "empty ifs: ${a[*]}"
unset IFS
echo "unset ifs: ${a[*]}"
