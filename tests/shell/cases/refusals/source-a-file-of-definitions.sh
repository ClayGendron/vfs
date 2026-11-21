# tier: language
# world: none
printf '%s\n' 'greeting=hello' 'say() { echo "$greeting $1"; }' >lib.sh
source ./lib.sh
say world
