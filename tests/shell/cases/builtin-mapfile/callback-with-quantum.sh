# tier: language
# world: none
cb() { echo "cb index=$1 line=[$2]"; }
mapfile -t -c 2 -C cb arr <<< $'a\nb\nc\nd\ne'
echo "count=${#arr[@]}"
