# tier: language
# world: none
set --
printf '[%s]\n' "$@" end
printf '[%s]\n' "x$@y"
set -- "$@"
echo "count=$#"
