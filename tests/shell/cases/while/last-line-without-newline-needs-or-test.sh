# tier: language
# world: none
printf 'one\ntwo' > in.txt
while IFS= read -r l; do echo "plain [$l]"; done < in.txt
while IFS= read -r l || [ -n "$l" ]; do echo "with test [$l]"; done < in.txt
