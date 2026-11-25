# tier: program
# world: seed
mkdir out
for f in docs/*.md; do sed 's/alpha/ALPHA/g' "$f" > "out/${f##*/}"; done
grep -c ALPHA out/*.md
