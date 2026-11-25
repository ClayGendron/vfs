# tier: language
# world: none
set -- -a -b value -c rest1 rest2
while getopts ab:c opt; do
  case $opt in
    b) echo "b with $OPTARG" ;;
    *) echo "flag $opt" ;;
  esac
done
shift $((OPTIND - 1))
echo "remaining: $*"
