# tier: language
# world: none
set -- -f
getopts :f: opt
echo "status=$? opt=$opt OPTARG=[${OPTARG-unset}]"
