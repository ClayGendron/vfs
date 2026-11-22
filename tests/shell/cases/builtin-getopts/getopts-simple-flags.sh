# tier: language
# world: none
set -- -a -b
while getopts ab opt; do
  echo "opt=$opt"
done
echo "OPTIND=$OPTIND"
