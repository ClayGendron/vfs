# tier: language
# world: none
if echo data | read -r; then echo "read from pipe succeeded"; fi
if true | false; then echo "wrong"; else echo "last stage failed"; fi
