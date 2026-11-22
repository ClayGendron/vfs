# tier: language
# world: none
set -- -a -b x y
while getopts ab opt; do :; done
shift $((OPTIND - 1))
echo "count=$#"
printf '[%s]\n' "$@"
