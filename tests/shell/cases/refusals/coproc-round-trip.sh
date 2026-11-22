# tier: language
# world: none
coproc { read -r line; echo "got $line"; }
echo ping >&"${COPROC[1]}"
read -r reply <&"${COPROC[0]}"
echo "$reply"
wait
