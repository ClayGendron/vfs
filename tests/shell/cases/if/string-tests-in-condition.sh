# tier: language
# world: none
s=abc e=
if [ "$s" = abc ]; then echo "equal"; fi
if [ "$s" != xyz ]; then echo "not equal"; fi
if [ -z "$e" ]; then echo "empty is -z"; fi
if [ -n "$s" ]; then echo "nonempty is -n"; fi
