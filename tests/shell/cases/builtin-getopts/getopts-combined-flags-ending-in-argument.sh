# tier: language
# world: none
set -- -vf out.txt rest
while getopts vf: opt; do
  echo "opt=$opt arg=[${OPTARG-}]"
done
shift $((OPTIND - 1))
echo "operands: $*"
