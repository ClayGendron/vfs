# tier: language
# world: none
count() { case $# in 0) echo none ;; 1) echo one ;; *) echo "many ($#)" ;; esac; }
count; count a; count a b c
