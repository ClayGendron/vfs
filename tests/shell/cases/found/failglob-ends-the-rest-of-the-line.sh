# tier: language
# world: none
shopt -s failglob; for f in .*; do echo "g:$f"; done; echo same-line
echo next-line
f() { shopt -s failglob; echo *.none; echo in-function; }; f; echo after-call
echo last
