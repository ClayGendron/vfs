# tier: language
# world: none
declare -u s=hello
echo "s=$s"
s+=" world"
echo "appended=$s"
declare -p s
