# tier: language
# world: none
set -- a 'b c' d
echo "$*"
IFS=,
echo "$*"
IFS=':;'
echo "$*"
