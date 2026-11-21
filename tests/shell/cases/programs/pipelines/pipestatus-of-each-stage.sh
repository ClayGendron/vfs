# tier: program
# world: seed
grep zebra docs/notes.txt | sort | head -n 1
echo "ps=${PIPESTATUS[*]}"
