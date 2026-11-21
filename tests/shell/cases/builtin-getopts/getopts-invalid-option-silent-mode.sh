# tier: language
# world: none
set -- -z
getopts :ab opt
echo "status=$? opt=$opt OPTARG=[${OPTARG-unset}]"
