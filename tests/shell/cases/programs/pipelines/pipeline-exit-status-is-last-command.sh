# tier: program
# world: seed
grep zebra docs/notes.txt | sort
echo "status=$?"
sort docs/notes.txt | grep zebra
echo "status=$?"
