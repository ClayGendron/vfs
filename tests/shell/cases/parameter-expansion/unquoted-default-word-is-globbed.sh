# tier: language
# world: seed
unset x
printf '[%s]\n' ${x:-docs/*.md}
printf '[%s]\n' "${x:-docs/*.md}"
