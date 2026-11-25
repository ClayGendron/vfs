# tier: language
# world: none
set -- -o out.txt -q -x input
quiet=no output=
while getopts :o:q opt; do
  case $opt in
    o) output=$OPTARG ;;
    q) quiet=yes ;;
    \?) echo "unknown -$OPTARG" ;;
  esac
done
shift $((OPTIND - 1))
echo "output=$output quiet=$quiet rest=$*"
