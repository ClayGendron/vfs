# tier: language
# world: none
if x=$(exit 2); then echo yes; else echo "no $?"; fi
if y=$(echo ok); then echo "yes [$y]"; fi
