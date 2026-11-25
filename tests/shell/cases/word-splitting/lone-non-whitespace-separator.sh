# tier: language
# world: none
IFS=:
v=':'
set -- $v
echo "one colon: $#"
v='::'
set -- $v
echo "two colons: $#"
printf '[%s]\n' "$@"
