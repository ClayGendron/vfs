# tier: language
# world: seed
compgen -G 'docs/*.md'
compgen -G '*.nomatch'
echo "status=$?"
