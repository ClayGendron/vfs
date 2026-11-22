# tier: language
# world: none
x=2
if [ "$x" -eq 1 ]; then echo one
elif [ "$x" -eq 2 ]; then echo two
elif [ "$x" -ge 2 ]; then echo "two or more"
else echo other
fi
