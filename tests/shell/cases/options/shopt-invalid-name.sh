# tier: language
# world: none
shopt -s nosuchopt 2>/dev/null
echo "status=$?"
shopt -q nosuchopt 2>/dev/null
echo "q status=$?"
