# tier: language
# world: none
pat='a*'
case abc in $pat) echo "unquoted \$pat globbed" ;; esac
case abc in "$pat") echo "never" ;; *) echo "quoted \$pat is literal" ;; esac
case 'a*' in "$pat") echo "quoted \$pat matched a literal a*" ;; esac
