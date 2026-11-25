# tier: language
# world: none
if [ zebra > apple ]; then echo "test said true"; fi
read -r x < apple
echo "read status=$? content=[$x]"
[ zebra \> apple ] && echo "escaped compares strings"
