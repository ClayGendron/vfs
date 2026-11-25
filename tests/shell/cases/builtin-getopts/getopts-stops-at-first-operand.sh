# tier: language
# world: none
set -- -a operand -b
while getopts ab opt; do echo "opt=$opt"; done
echo "OPTIND=$OPTIND"
