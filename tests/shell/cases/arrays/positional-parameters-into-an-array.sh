# tier: language
# world: none
set -- x "y z" ""
args=("$@")
echo "count=${#args[@]}"
printf '[%s]\n' "${args[@]}"
