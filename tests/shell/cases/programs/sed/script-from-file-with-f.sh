# tier: program
# world: seed
printf 's/alpha/A/\n/second/d\n' > script.sed
sed -f script.sed docs/a.md
