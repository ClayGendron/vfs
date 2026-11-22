# tier: language
# world: none
# stderr: exact
echo original > f
set -C
echo replaced 2>err2.txt > f
IFS= read -r msg < err2.txt
echo "msg=[$msg]"
