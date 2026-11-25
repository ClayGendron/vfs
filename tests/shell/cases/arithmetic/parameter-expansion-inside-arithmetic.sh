# tier: language
# world: none
s=hello
echo $(( ${#s} * 2 ))
unset u
echo $(( ${u:-5} + 1 ))
