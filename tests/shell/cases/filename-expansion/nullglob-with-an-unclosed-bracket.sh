# tier: language
# world: none
shopt -s nullglob
: > a
printf '[%s]\n' [a "x[" '[b'
