# tier: program
# world: seed
printf 'x\t3\ny\t1\nz\t2\n' | sort -t "$(printf '\t')" -k2,2n
