# tier: language
# world: none
count() { echo "$#"; }
set --
count "$@"
count "x$@"
count "$*"
