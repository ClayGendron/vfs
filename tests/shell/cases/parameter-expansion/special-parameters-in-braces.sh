# tier: language
# world: none
set -- one two
echo "count=${#} first=${1} all=${@} star=${*}"
false
echo "status=${?}"
