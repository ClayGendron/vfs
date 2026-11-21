# tier: language
# world: none
set -- -z
getopts ab opt 2>&1
echo "status=$? opt=$opt OPTARG=[${OPTARG-unset}]"
