# tier: language
# world: none
shopt -s extglob
: > a.md; : > ab.md; : > b.md; : > abab.md
printf '[%s]\n' a?(b).md
