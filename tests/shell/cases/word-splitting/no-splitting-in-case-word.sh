# tier: language
# world: none
v='a b'
case $v in
  'a b') echo "matched whole" ;;
  *) echo "split" ;;
esac
