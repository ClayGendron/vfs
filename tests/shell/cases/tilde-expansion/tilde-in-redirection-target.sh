# tier: language
# world: none
HOME=$PWD
echo written > ~/out.txt
while IFS= read -r line; do echo "read: $line"; done < out.txt
