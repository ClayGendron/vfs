# tier: language
# world: none
: > a.txt
{ for f in *; do echo "g:$f"; done; } > out.txt
cat out.txt
