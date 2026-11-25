# tier: language
# world: none
case b in
  {a,b}) echo "matched braces" ;;
  *) echo "no brace expansion" ;;
esac
case '{a,b}' in
  {a,b}) echo "literal match" ;;
esac
