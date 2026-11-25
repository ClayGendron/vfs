# tier: language
# world: none
set_it() { value=changed; }
value=original
echo | set_it
echo "after pipeline: $value"
set_it
echo "after direct call: $value"
