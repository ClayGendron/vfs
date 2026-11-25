# tier: program
# world: seed
grep -n 'line' docs/a.md | cut -d: -f1 | tr '\n' ' '
echo
