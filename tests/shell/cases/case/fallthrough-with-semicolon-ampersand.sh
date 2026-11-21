# tier: language
# world: none
case b in
  a) echo "a" ;;
  b) echo "b" ;&
  c) echo "c (fell through)" ;&
  d) echo "d (fell through)" ;;
  e) echo "e never" ;;
esac
