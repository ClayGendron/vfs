# tier: language
# world: none
arr=([1]=a [5]=b [9]=c)
echo "[${arr[@]:2}]"
echo "[${arr[@]:0:2}]"
