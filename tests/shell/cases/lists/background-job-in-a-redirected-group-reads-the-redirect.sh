# tier: language
# world: none
{ read -r x & wait $!; echo "read in background: $?"; } <<< "from here-string"
