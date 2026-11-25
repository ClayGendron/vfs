# tier: language
# world: none
echo hello > out.txt
echo "status=$?"
IFS= read -r line < out.txt
echo "line=[$line]"
