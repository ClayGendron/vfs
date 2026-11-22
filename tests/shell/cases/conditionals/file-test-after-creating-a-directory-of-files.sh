# tier: language
# world: seed
for p in data data/people.csv data/none logs/app.log; do
  if [[ -d $p ]]; then echo "$p: directory"
  elif [[ -f $p ]]; then echo "$p: file"
  else echo "$p: missing"; fi
done
