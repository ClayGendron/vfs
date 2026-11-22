# tier: language
# world: none
echo from-file > in.txt
echo from-pipe | { read -r x; echo "x=[$x]"; } < in.txt
