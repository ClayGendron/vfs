# tier: language
# world: none
printf 'b\na\n' > >(while IFS= read -r l; do echo "<$l>"; done > out.txt)
wait $!
while IFS= read -r l; do echo "file: $l"; done < out.txt
