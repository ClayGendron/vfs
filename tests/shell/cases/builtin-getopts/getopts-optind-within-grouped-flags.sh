# tier: language
# world: none
set -- -ab -c
getopts abc opt; echo "$opt OPTIND=$OPTIND"
getopts abc opt; echo "$opt OPTIND=$OPTIND"
getopts abc opt; echo "$opt OPTIND=$OPTIND"
