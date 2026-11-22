# tier: language
# world: none
echo piped | { read -r x & wait $!; echo "read in background: $?"; }
