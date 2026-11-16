/// Intersect two sorted posting lists of document ids (the shape of a lexical AND).
pub fn intersect(a: &[u32], b: &[u32]) -> Vec<u32> {
    let (mut i, mut j, mut out) = (0, 0, Vec::new());
    while i < a.len() && j < b.len() {
        if a[i] == b[j] { out.push(a[i]); i += 1; j += 1; }
        else if a[i] < b[j] { i += 1 } else { j += 1 }
    }
    out
}

/// A midpoint for binary search over doc ids, written the classic overflowing way.
pub fn midpoint(lo: u32, hi: u32) -> u32 { (lo + hi) / 2 }

#[cfg(kani)]
mod proofs {
    use super::*;
    #[kani::proof]
    #[kani::unwind(6)]
    fn intersect_is_sound() {
        let a: [u32; 4] = kani::any();
        let b: [u32; 4] = kani::any();
        kani::assume(a.windows(2).all(|w| w[0] < w[1]) && b.windows(2).all(|w| w[0] < w[1]));
        let out = intersect(&a, &b);
        for x in &out { assert!(a.contains(x) && b.contains(x)); }
        for x in &a { if b.contains(x) { assert!(out.contains(x)); } }
    }
    #[kani::proof]
    fn midpoint_never_panics() {
        let lo: u32 = kani::any();
        let hi: u32 = kani::any();
        kani::assume(lo <= hi);
        let m = midpoint(lo, hi);
        assert!(lo <= m && m <= hi);
    }
}

pub fn midpoint_fixed(lo: u32, hi: u32) -> u32 { lo + (hi - lo) / 2 }

#[cfg(kani)]
mod proofs_fixed {
    use super::*;
    #[kani::proof]
    fn midpoint_fixed_in_range() {
        let lo: u32 = kani::any();
        let hi: u32 = kani::any();
        kani::assume(lo <= hi);
        let m = midpoint_fixed(lo, hi);
        assert!(lo <= m && m <= hi);
    }
    #[kani::proof]
    #[kani::unwind(5)]
    fn intersect_small() {
        let a: [u32; 2] = kani::any();
        let b: [u32; 2] = kani::any();
        kani::assume(a[0] < a[1] && b[0] < b[1]);
        let out = intersect(&a, &b);
        for x in &out { assert!(a.contains(x) && b.contains(x)); }
    }
}
