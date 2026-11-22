# tier: program
# world: seed
cp docs/a.md one.md
cp docs/b.md two.md
sed -i '1d' one.md two.md
cat one.md two.md
