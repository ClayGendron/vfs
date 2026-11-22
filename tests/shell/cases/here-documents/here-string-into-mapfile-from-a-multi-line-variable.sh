# tier: language
# world: none
data=$'a\nb\nc'
mapfile -t lines <<< "$data"
echo "count=${#lines[@]} last=${lines[-1]}"
