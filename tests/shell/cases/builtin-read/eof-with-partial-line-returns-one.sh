# tier: language
# world: none
printf 'abc' | { read x; echo "status=$? x=[$x]"; }
