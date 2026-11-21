# tier: language
# world: none
echo data | { read -r v; echo "saw $v"; } > out.txt
IFS= read -r line < out.txt
echo "file: $line"
