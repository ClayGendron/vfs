# tier: language
# world: none
read -n 4 -d , x <<< "ab,cdef"
echo "x=[$x]"
read -n 2 -d , y <<< "abcd,ef"
echo "y=[$y]"
