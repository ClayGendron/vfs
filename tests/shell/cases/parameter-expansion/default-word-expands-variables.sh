# tier: language
# world: none
unset x
y=other
echo "${x:-$y/path}"
