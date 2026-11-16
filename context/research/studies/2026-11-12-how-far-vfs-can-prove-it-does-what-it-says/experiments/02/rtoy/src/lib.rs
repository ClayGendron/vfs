/// The tighter of two caps, never below one.
pub fn membership_budget(in_list: usize, params: usize) -> usize {
    let b = if in_list < params { in_list } else { params };
    if b == 0 { 1 } else { b }
}

/// Slice `n` items into chunks no larger than `size`; returns chunk lengths.
pub fn chunk_lengths(n: usize, size: usize) -> Vec<usize> {
    let mut out = Vec::new();
    let mut left = n;
    while left > 0 {
        let take = if left > size { size } else { left };
        out.push(take);
        left -= take;
    }
    out
}

/// A caller may read a path when it holds a grant on that path or an ancestor.
pub fn may_read(grants: &[&str], path: &str) -> bool {
    grants.iter().any(|g| path == *g || path.starts_with(&format!("{}/", g)))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn budget_takes_a_cap() { assert!(membership_budget(1000, 2100) <= 1000); }
    #[test]
    fn budget_zero() { assert_eq!(membership_budget(0, 5), 1); }
    #[test]
    fn chunks_cover() { assert_eq!(chunk_lengths(2500, 1000).iter().sum::<usize>(), 2500); }
    #[test]
    fn grant_on_self() { assert!(may_read(&["/a"], "/a")); }
    #[test]
    fn grant_on_parent() { assert!(may_read(&["/a"], "/a/b")); }
}

/// The planted bug: a grant on /a also opens /ab.
pub fn may_read_buggy(grants: &[&str], path: &str) -> bool {
    grants.iter().any(|g| path.starts_with(*g))
}
