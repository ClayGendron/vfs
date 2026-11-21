# tier: language
# world: none
x=$(echo kept; exit 4; echo dropped)
echo "x=$x status=$?"
