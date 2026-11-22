# tier: language
# world: none
set -- -f file.txt -v
while getopts f:v opt; do
  echo "opt=$opt arg=[${OPTARG-unset}]"
done
echo "OPTIND=$OPTIND"
