# tier: language
# world: none
x=$(case yes in (yes) echo matched;; (*) echo other;; esac)
echo "[$x]"
