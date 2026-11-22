# tier: language
# world: seed
shopt -s extglob
printf '[%s]\n' data/@(*.csv|w*)
