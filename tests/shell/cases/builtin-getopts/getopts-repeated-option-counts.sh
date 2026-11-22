# tier: language
# world: none
set -- -v -v -vv
verbose=0
while getopts v opt; do verbose=$((verbose + 1)); done
echo "verbose=$verbose"
