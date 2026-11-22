# tier: language
# world: none
a=1
b=2
declare -p a nosuch b 2>/dev/null
echo "status=$?"
