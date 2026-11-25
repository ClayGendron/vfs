# tier: program
# world: seed
mkdir -p build/out
cp docs/notes.txt build/notes.txt
sed -i 's/TODO/DONE/' build/notes.txt
mv build/notes.txt build/out/
rm -r docs
find build | sort
grep -c DONE build/out/notes.txt
