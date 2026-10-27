//! sha256 throughput in Rust at the sizes the Python probe used, plus a fused
//! "decode + hash" pass (UTF-8 validation and hashing over the same bytes once)
//! against the two-pass form (validate, then hash).
use sha2::{Digest, Sha256};
use std::time::Instant;

const SIZES: [usize; 6] = [1_000, 10_000, 100_000, 1_000_000, 4_000_000, 16_000_000];
const REPS: u32 = 20;

fn body(n: usize) -> Vec<u8> {
    let line = [b'x'; 99];
    let mut v = Vec::with_capacity(n);
    while v.len() + 100 <= n {
        v.extend_from_slice(&line);
        v.push(b'\n');
    }
    v
}

fn hash(data: &[u8]) -> [u8; 32] {
    Sha256::digest(data).into()
}

fn two_pass(data: &[u8]) -> ([u8; 32], usize) {
    let text = std::str::from_utf8(data).unwrap();
    let lines = text.bytes().filter(|&b| b == b'\n').count();
    (hash(data), lines)
}

fn fused(data: &[u8]) -> ([u8; 32], usize) {
    // One sweep: validate UTF-8 in chunks, count newlines and feed the hasher as we go.
    let mut h = Sha256::new();
    let mut lines = 0usize;
    for chunk in data.chunks(64 * 1024) {
        std::str::from_utf8(chunk).unwrap();
        lines += chunk.iter().filter(|&&b| b == b'\n').count();
        h.update(chunk);
    }
    (h.finalize().into(), lines)
}

fn time<F: FnMut() -> R, R>(mut f: F) -> f64 {
    let t0 = Instant::now();
    for _ in 0..REPS {
        std::hint::black_box(f());
    }
    t0.elapsed().as_secs_f64() / REPS as f64 * 1e6
}

fn main() {
    println!("{:>12} {:>12} {:>12} {:>12} {:>10}", "bytes", "sha256 µs", "two-pass µs", "fused µs", "GB/s");
    for &n in &SIZES {
        let d = body(n);
        let _ = hash(&d);
        let h = time(|| hash(&d));
        let t = time(|| two_pass(&d));
        let f = time(|| fused(&d));
        println!("{:>12} {:>12.0} {:>12.0} {:>12.0} {:>10.2}", d.len(), h, t, f, d.len() as f64 / h / 1e3);
    }
}
