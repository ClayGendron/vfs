# tier: language
# world: none
printf 'abc\\' | { read x; echo "status=$? x=[$x]"; }
printf 'abc\\' | { read -r x; echo "status=$? x=[$x]"; }
