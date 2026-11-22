# tier: language
# world: none
unset x
( : "${x:?missing}" )
echo "status=$?"
