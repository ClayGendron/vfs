# tier: language
# world: none
a=()
a[010]=eight
a[07]=seven
echo "indices=${!a[*]}"
a[08]=bad
echo "status=$?"
