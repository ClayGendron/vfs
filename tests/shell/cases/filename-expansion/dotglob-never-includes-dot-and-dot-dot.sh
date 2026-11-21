# tier: language
# world: seed
shopt -s dotglob
for f in *; do case $f in .|..) echo "found $f" ;; esac; done
echo "checked"
