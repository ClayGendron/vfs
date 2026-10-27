//! alloc — grow a vector one MiB at a time until the host says no.
fn main() {
    let mut v: Vec<u8> = Vec::new();
    let mut mib = 0usize;
    loop {
        v.extend_from_slice(&[0u8; 1 << 20]);
        mib += 1;
        if mib % 16 == 0 {
            eprintln!("alloc: {} MiB", mib);
        }
        std::hint::black_box(&v);
    }
}
