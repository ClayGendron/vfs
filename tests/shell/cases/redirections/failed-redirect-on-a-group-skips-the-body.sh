# tier: language
# world: none
ran=no
{ ran=yes; echo inside; } > nodir/out
echo "status=$? ran=$ran"
