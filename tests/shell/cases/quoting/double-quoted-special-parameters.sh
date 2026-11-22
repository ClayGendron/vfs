# tier: language
# world: none
set -- p q
printf '[%s]\n' "$#" "$1" "${#1}" "$0"
true
echo "status in quotes: $?"
