# tier: language
# world: none
set -- a b c
printf '[%s]\n' "${@:1:0}"
echo "done"
