# tier: language
# world: none
shopt -s extglob
: > a.md; : > ab.md; : > abb.md; : > ac.md
printf '[%s]\n' a+(b).md
