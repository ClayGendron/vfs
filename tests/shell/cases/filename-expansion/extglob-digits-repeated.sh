# tier: language
# world: none
shopt -s extglob
: > v1; : > v12; : > v1a; : > v
printf '[%s]\n' v+([0-9])
