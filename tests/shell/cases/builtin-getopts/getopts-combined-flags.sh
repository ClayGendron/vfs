# tier: language
# world: none
set -- -abc
while getopts abc opt; do
  echo "opt=$opt OPTIND=$OPTIND"
done
