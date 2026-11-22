# tier: language
# world: none
x=$(echo ab | { read -r v; echo "$v$v"; })
echo "x=$x"
y=$(false | true)
echo "status=$?"
