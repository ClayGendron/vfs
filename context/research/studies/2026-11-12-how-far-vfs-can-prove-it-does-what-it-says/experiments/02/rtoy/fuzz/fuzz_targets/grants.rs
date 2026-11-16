#![no_main]
use libfuzzer_sys::fuzz_target;

fn model(grant: &str, path: &str) -> bool {
    let mut prefix = String::new();
    for part in path.split('/').filter(|p| !p.is_empty()) {
        prefix.push('/');
        prefix.push_str(part);
        if prefix == grant { return true; }
    }
    false
}

fuzz_target!(|data: (&str, &str)| {
    let (g, p) = data;
    let grant = format!("/{}", g.trim_matches('/'));
    let path = format!("/{}", p.trim_matches('/'));
    if grant == "/" || path.contains("//") || grant.contains("//") { return; }
    assert_eq!(rtoy::may_read(&[grant.as_str()], &path), model(&grant, &path));
});
