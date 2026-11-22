# tier: language
# world: none
nosuchcommand 2> err.txt
echo "status=$?"
IFS= read -r msg < err.txt
echo "msg=[$msg]"
