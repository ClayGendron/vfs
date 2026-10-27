//! spin — never returns; the timeout fixture.
fn main() {
    let mut x: u64 = 0;
    loop {
        x = x.wrapping_add(1);
        std::hint::black_box(x);
    }
}
