# tier: language
# world: none
local x=1 2>&1
echo "status=$?"
echo "x=[${x-unset}]"
