# tier: language
# world: none
(exec > hidden.txt; echo "into file")
echo "back on stdout"
read -r l < hidden.txt
echo "file: $l"
