# tier: language
# world: none
if [ abc -lt 5 ] 2>/dev/null; then echo "then"; else echo "else (status $?)"; fi
