# tier: program
# world: none
cat <<EOF
outer $(cat <<INNER
inner
INNER
) end
EOF
