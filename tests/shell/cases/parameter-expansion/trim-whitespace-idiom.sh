# tier: language
# world: none
x='   hello world  '
x="${x#"${x%%[![:space:]]*}"}"
x="${x%"${x##*[![:space:]]}"}"
echo "[$x]"
