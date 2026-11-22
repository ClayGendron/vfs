# tier: language
# world: none
set -- -f
getopts f: opt 2>&1
echo "status=$? opt=$opt OPTARG=[${OPTARG-unset}]"
