# tier: language
# world: none
arr=(a b c)
( echo "[${arr[-5]}]"; echo "reached" )
echo "status=$?"
