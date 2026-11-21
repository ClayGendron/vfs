# tier: language
# world: none
a=1 b=
if [ -n "$a" ] && [ -z "$b" ]; then echo "a set, b empty"; fi
if [ -n "$b" ] || [ "$a" = 1 ]; then echo "either"; fi
