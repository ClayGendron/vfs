# tier: language
# world: none
declare -a a=('one two' '' 'a"quote')
declare -p a
echo "count=${#a[@]}"
