# tier: program
# world: seed
head -n 0 docs/a.md
echo "status=$? out=[$(head -n 0 docs/a.md)]"
