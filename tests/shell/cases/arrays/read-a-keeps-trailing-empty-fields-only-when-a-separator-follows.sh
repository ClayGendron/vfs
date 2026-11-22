# tier: language
# world: none
IFS=, read -r -a f1 <<< "a,b,"
IFS=, read -r -a f2 <<< "a,b,,"
echo "f1=${#f1[@]} f2=${#f2[@]}"
