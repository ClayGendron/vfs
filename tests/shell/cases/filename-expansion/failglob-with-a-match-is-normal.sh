# tier: language
# world: seed
shopt -s failglob
printf '[%s]\n' docs/*.md
echo "status=$?"
