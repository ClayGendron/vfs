# tier: language
# world: none
set -- -a -- -b file
while getopts ab opt; do echo "opt=$opt"; done
echo "OPTIND=$OPTIND"
shift $((OPTIND - 1))
printf '[%s]\n' "$@"
