# tier: language
# world: none
set -- -f val -v
getopts f:v opt
echo "after f: [${OPTARG-unset}]"
getopts f:v opt
echo "after v: [${OPTARG-unset}]"
