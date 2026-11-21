# tier: language
# world: none
if ! false; then echo "negated false"; fi
if ! [ a = a ]; then echo "wrong"; else echo "negated true goes to else"; fi
