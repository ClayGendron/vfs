# tier: language
# world: none
declare 1x=2 2>/dev/null
echo "status=$?"
declare 'a-b=1' 2>&1
echo "status=$?"
