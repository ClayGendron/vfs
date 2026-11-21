# tier: language
# world: none
case abc in
  a*) echo "starts with a" ;;&
  *b*) echo "contains b" ;;&
  x*) echo "never" ;;&
  *c) echo "ends with c" ;;
  *) echo "never reached" ;;
esac
