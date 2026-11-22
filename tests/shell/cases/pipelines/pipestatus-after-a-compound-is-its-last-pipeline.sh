# tier: language
# world: none
{ false | true; }
echo "group: ${PIPESTATUS[*]}"
for i in 1; do false | (exit 3); done
echo "for: ${PIPESTATUS[*]}"
case x in x) false | true;; esac
echo "case: ${PIPESTATUS[*]}"
