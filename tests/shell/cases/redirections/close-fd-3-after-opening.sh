# tier: language
# world: none
{ echo ok >&3; } 3> f 3>&-
echo "status=$?"
mapfile -t lines < f
echo "lines in f=${#lines[@]}"
