# tier: language
# world: none
# stderr: exact
echo hi 2>err.txt >&7
echo "status=$?"
IFS= read -r msg < err.txt
echo "msg=[$msg]"
