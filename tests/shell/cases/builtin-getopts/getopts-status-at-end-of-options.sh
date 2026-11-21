# tier: language
# world: none
set -- -a
getopts a opt
echo "first status=$? opt=$opt"
getopts a opt
echo "end status=$? opt=$opt OPTIND=$OPTIND"
