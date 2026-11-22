# tier: language
# world: none
case a in
  a)
    case b in
      b) echo "inner b" ;;
    esac
    echo "after inner"
    ;;
esac
