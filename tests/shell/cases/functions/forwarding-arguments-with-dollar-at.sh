# tier: language
# world: none
inner() { printf '<%s>' "$@"; echo " n=$#"; }
outer() { inner "$@"; inner "$*"; inner $@; }
outer "a b" c
