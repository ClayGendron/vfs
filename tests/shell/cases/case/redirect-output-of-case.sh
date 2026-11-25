# tier: language
# world: none
case a in a) echo "into file" ;; esac > out.txt
read -r l < out.txt
echo "file: $l"
