# tier: language
# world: seed
mapfile -t words < data/words.txt
echo "count=${#words[@]} first=${words[0]} last=${words[-1]}"
