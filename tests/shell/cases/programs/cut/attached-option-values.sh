# tier: program
# world: seed
cut -d: -f1 <<< 'user:x:1000'
cut -d : -f 3 <<< 'user:x:1000'
cut -d':' -f'2' <<< 'user:x:1000'
