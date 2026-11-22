# tier: language
# world: none
set -- a b c
shift
echo "count=$# first=$1"
printf '[%s]\n' "$@"
