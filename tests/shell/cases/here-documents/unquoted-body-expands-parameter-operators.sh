# tier: language
# world: none
unset missing
s=filename.tar.gz
while IFS= read -r line; do echo "$line"; done <<EOF
default: ${missing:-dflt}
length: ${#s}
suffix: ${s%%.*}
replace: ${s//./_}
EOF
