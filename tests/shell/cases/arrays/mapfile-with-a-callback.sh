# tier: language
# world: none
report() { echo "callback: index=$1 line=[$2]"; }
mapfile -t -c 2 -C report lines <<< $'l0\nl1\nl2\nl3\nl4'
echo "count=${#lines[@]}"
