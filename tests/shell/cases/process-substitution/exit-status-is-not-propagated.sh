# tier: language
# world: none
read -r x < <(echo data; exit 3)
echo "status=$? x=[$x]"
