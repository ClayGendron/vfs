# tier: language
# world: none
echo "to the reader" > >(while IFS= read -r l; do echo "got [$l]"; done)
wait $!
echo "after wait"
