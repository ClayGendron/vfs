# tier: language
# world: none
set -- --long
getopts :ab opt
echo "status=$? opt=$opt OPTARG=[${OPTARG-}]"
