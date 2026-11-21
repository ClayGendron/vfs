# tier: language
# world: none
x='*'
case abc in "$x") echo "quoted: match" ;; *) echo "quoted: no match" ;; esac
case abc in $x) echo "unquoted: match" ;; *) echo "unquoted: no match" ;; esac
case '*' in '*') echo "literal star matches star" ;; esac
case 'a?' in a\?) echo "escaped question mark" ;; esac
