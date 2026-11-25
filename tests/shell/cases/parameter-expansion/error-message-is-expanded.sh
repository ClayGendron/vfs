# tier: language
# world: none
# stderr: exact
unset x
what=config
: "${x:?need $what file}"
