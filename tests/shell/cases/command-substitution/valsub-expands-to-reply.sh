# tier: language
# world: none
x=${| REPLY=computed; }
echo "x=[$x]"
echo "reply=[${REPLY-unset}]"
