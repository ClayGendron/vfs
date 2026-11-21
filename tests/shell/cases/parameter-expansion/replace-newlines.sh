# tier: language
# world: none
x=$'line1\nline2\nline3'
echo "${x//$'\n'/, }"
