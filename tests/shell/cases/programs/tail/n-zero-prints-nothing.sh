# tier: program
# world: seed
tail -n 0 docs/a.md
echo "status=$? [$(tail -n 0 docs/a.md)]"
