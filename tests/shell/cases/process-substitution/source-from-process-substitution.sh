# tier: language
# world: none
source <(echo 'v=42'; echo 'g() { echo "g says $1"; }')
echo "v=$v"
g hi
