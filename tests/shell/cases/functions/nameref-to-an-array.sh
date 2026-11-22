# tier: language
# world: none
append() { local -n arr=$1; arr+=("$2"); }
list=(a)
append list b
append list "c d"
printf '[%s]\n' "${list[@]}"
