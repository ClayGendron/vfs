# tier: program
# world: seed
mkdir -p out
cat docs/b.md | tee out/b.copy | wc -l
cat out/b.copy
