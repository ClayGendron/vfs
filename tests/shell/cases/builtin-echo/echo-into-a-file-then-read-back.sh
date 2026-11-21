# tier: language
# world: none
echo -e 'line1\nline2' > out.txt
echo -n 'line3' >> out.txt
while IFS= read -r l || [ -n "$l" ]; do echo "[$l]"; done < out.txt
