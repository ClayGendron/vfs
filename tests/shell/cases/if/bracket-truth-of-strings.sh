# tier: language
# world: none
if [ "" ]; then echo "empty true"; else echo "empty string is false"; fi
if [ x ]; then echo "nonempty string is true"; fi
if [ ]; then echo "wrong"; else echo "no arguments is false"; fi
