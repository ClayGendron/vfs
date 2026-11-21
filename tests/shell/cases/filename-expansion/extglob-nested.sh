# tier: language
# world: none
shopt -s extglob
: > x.tar.gz; : > x.tar; : > x.gz; : > x.zip
printf '[%s]\n' x.@(tar?(.gz)|zip)
