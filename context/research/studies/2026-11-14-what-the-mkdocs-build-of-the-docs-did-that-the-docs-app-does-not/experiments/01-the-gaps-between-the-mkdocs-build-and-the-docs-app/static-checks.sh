G=/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/96ca7b12-ae8e-42f1-8e39-f71cf4e99e78/scratchpad/gap-study
O=$G/old-site; N=$G/new-site
echo "== snippets marker in pages: $(grep -rl -e '--8<--' --include='*.md' /Users/claygendron/Git/Repos/vfs/documentation | wc -l | tr -d ' ')"
echo "== OLD top-level files"; ls $O; echo "== NEW top-level files"; ls $N
echo "== OLD head of overview"; grep -oE '<(title|meta|link)[^>]*>([^<]*</title>)?' $O/overview/index.html | cut -c1-220
echo "== NEW head of overview"; grep -oE '<(title|meta|link)[^>]*>([^<]*</title>)?' $N/overview.html | cut -c1-220 | grep -v modulepreload
echo "== NEW modulepreload count: $(grep -oE '<link[^>]*modulepreload[^>]*>' $N/overview.html | wc -l)"
echo "== OLD sitemap entries: $(grep -c '<loc>' $O/sitemap.xml)"; head -c 400 $O/sitemap.xml; echo
echo "== NEW sitemap/robots:"; ls $N/sitemap.xml $N/robots.txt 2>&1
echo "== OLD 404 title"; grep -oE '<title>[^<]*</title>' $O/404.html; echo "== NEW 404 title"; grep -oE '<title>[^<]*</title>' $N/404.html
echo "== OLD search index"; ls -la $O/search; python3 -c "
import json;d=json.load(open('$O/search/search_index.json'));print('docs in index',len(d['docs']));print(d['config'])"
echo "== NEW any search"; grep -rlis 'search' $N --include='*.html' | head -3; echo "(end)"
echo "== OLD objects.inv bytes: $(wc -c < $O/objects.inv)"; ls $N | grep -i inv
echo "== OLD permalinks on overview: $(grep -o 'class="headerlink"' $O/overview/index.html | wc -l)"; grep -oE '<a class="headerlink"[^>]*>[^<]*</a>' $O/overview/index.html | head -2
echo "== NEW heading anchors on overview"; grep -oE '<h2[^>]*>.{0,120}' $N/overview.html | head -2
echo "== OLD external link attrs"; grep -oE '<a [^>]*href="https://(www.gartner|github.com/ClayGendron/vfs/blob)[^>]*>' $O/overview/index.html $O/reference/glossary/index.html | head -3
echo "== NEW external link attrs"; grep -oE '<a [^>]*href="https://(www.gartner|github.com/ClayGendron/vfs/blob)[^>]*>' $N/overview.html $N/reference/glossary.html | head -3
echo "== OLD vfs-new-tab span: $(grep -c 'id="vfs-new-tab"' $O/overview/index.html)"
echo "== OLD skip link"; grep -oE '<a [^>]*md-skip[^>]*>[^<]*' $O/overview/index.html; echo "== NEW skip link"; grep -oiE '<a [^>]*skip[^>]*>[^<]*' $N/overview.html
echo "== OLD back to top"; grep -oE '<button[^>]*md-top[^>]*>' $O/overview/index.html | cut -c1-200; echo "== NEW back to top"; grep -oiE 'back to top|scroll to top' $N/overview.html | head -1
echo "== OLD footer nav"; grep -oE '<a [^>]*md-footer__link[^>]*>' $O/overview/index.html | cut -c1-200; echo "== NEW pager"; grep -oE '<nav[^>]*docs-pager[^>]*>' $N/overview.html | cut -c1-200
echo "== OLD code copy (data-clipboard / content.code.copy in features)"; grep -oE '"features":\[[^]]*\]' $O/overview/index.html
echo "== NEW copy buttons in overview: $(grep -oE 'aria-label="Copy[^"]*"' $N/overview.html | sort | uniq -c)"
echo "== OLD noscript"; grep -oE '<noscript>.{0,200}' $O/overview/index.html | head -3; grep -c 'class="no-js"' $O/overview/index.html
echo "== NEW noscript"; grep -oE '<noscript>.{0,200}' $N/overview.html | head -3
echo "== OLD fonts served"; find $O/assets/external -type f | sed 's|.*/assets/external/||' | cut -d/ -f1 | sort | uniq -c
echo "== NEW fonts served"; find $N/_app -name '*.woff2' | wc -l; grep -rhoE 'https?://[a-z0-9.-]+' $N/overview.html | sort | uniq -c
echo "== OLD external hosts referenced in HTML"; grep -rhoE '(src|href)="https?://[a-z0-9.-]+' $O/overview/index.html | sort | uniq -c
echo "== OLD mermaid js"; find $O -name 'mermaid*'
echo "== OLD lang attr / NEW lang attr"; grep -oE '<html[^>]*>' $O/overview/index.html $N/overview.html
echo "== OLD print css"; grep -c '@media print' $O/assets/stylesheets/main.*.min.css; echo "== NEW print css"; cat $N/_app/immutable/assets/*.css | grep -o '@media print' | wc -l
echo "== OLD site sizes"; du -sh $O $N; echo "pages: old $(find $O -name index.html | wc -l) new $(find $N -name '*.html' | wc -l)"
echo "== OLD canonical on api page"; grep -oE '<link rel="(canonical|prev|next)"[^>]*>' $O/tutorials/use-the-cli/index.html
echo "== OLD generator/meta description on a tutorial"; grep -oE '<meta name="(description|generator|author)"[^>]*>' $O/tutorials/use-the-cli/index.html
