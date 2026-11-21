# tier: language
# world: none
e=
case $e in
  ?*) echo "nonempty" ;;
  "") echo "empty word matched \"\"" ;;
esac
case "" in '') echo "quoted empty matched ''" ;; esac
