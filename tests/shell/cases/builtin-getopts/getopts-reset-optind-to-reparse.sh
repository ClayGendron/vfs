# tier: language
# world: none
set -- -a -b
while getopts ab opt; do echo "first pass $opt"; done
OPTIND=1
while getopts ab opt; do echo "second pass $opt"; done
