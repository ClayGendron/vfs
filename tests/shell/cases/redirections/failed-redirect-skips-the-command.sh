# tier: language
# world: none
f() { echo "f ran"; ran=yes; }
ran=no
f > nodir/out
echo "status=$? ran=$ran"
