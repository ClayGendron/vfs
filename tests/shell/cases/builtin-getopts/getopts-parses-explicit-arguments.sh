# tier: language
# world: none
set -- positional
while getopts ab: opt -a -b val; do
  echo "opt=$opt arg=[${OPTARG-}]"
done
echo "positional kept: $1"
