# tier: language
# world: none
a=(apple "green pear" fig)
has() { local x; for x in "${a[@]}"; do [[ $x == "$1" ]] && return 0; done; return 1; }
has pear; echo "pear=$?"
has "green pear"; echo "green pear=$?"
