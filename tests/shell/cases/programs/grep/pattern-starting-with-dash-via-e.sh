# tier: program
# world: seed
printf -- '-v flag\nother\n' | grep -e '-v'
printf -- '-v flag\nother\n' | grep -- -v
