# tier: program
# world: seed
cp docs/a.md copy.md
sed -i.bak 's/alpha/ALPHA/g' copy.md
cat copy.md
echo ---
cat copy.md.bak
