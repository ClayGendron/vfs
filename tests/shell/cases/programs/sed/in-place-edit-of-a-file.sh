# tier: program
# world: seed
cp docs/notes.txt work.txt
sed -i 's/TODO/FIXME/' work.txt
echo "status=$?"
cat work.txt
