# tier: language
# world: none
# stderr: exact
readonly ro=old
printf -v ro '%s' new
echo "status=$? ro=$ro"
