# tier: language
# world: none
set -- -ffile.txt -v
while getopts f:v opt; do
  echo "opt=$opt arg=[${OPTARG-}]"
done
