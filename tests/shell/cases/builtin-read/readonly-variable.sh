# tier: language
# world: none
# stderr: exact
readonly ro=keep
read ro <<< "new"
echo "status=$? ro=$ro"
