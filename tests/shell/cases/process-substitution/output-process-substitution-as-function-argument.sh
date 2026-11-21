# tier: language
# world: none
emit() { printf 'one\ntwo\n' > "$1"; }
emit >(n=0; while read -r _; do n=$((n + 1)); done; echo "reader saw $n lines")
wait $!
echo done
