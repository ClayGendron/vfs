# tier: language
# world: none
case hello in
  h*) echo "h prefix" ;;&
  *) echo "default also ran" ;;
esac
