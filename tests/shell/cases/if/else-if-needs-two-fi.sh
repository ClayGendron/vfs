# tier: language
# world: none
x=b
if [ "$x" = a ]; then echo a
else if [ "$x" = b ]; then echo "nested b"; fi
fi
