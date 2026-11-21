# tier: language
# world: none
shopt -s extglob
for name in report.md report.txt notes.md; do
  if [[ $name == @(report|notes).md ]]; then echo "$name matches"; else echo "$name does not"; fi
done
