# tier: language
# world: none
unset target
echo hi > $target 2>err.txt
echo hi 2>err.txt > $target
echo "status=$?"
IFS= read -r msg < err.txt
echo "msg=[$msg]"
