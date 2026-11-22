# tier: language
# world: none
a=(src/main.py src/lib/util.py notes.txt)
echo "# ${a[@]#*/}"
echo "## ${a[@]##*/}"
echo "% ${a[@]%.*}"
echo "%% ${a[@]%%/*}"
