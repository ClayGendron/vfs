# tier: language
# world: none
# stderr: exact
readonly -a ro=(1 2)
mapfile -t ro <<< "x"
echo "status=$? ${ro[*]}"
