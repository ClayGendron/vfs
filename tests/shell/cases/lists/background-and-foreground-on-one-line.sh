# tier: language
# world: none
x=0; (exit 7) & x=1
wait $!
echo "job=$? x=$x"
