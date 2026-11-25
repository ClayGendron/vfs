# tier: language
# world: none
[ \( a = b -o c = c \) -a d = d ]; echo "grouped: $?"
[ a = b -o \( c = c -a d = e \) ]; echo "other grouping: $?"
