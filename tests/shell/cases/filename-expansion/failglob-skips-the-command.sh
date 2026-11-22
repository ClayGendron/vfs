# tier: language
# world: seed
shopt -s failglob
ran=no
f() { ran=yes; }
f *.nomatch
echo "status=$? ran=$ran"
