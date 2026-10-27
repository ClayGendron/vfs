//! upper IN OUT — read IN, uppercase it, write OUT, print the line count.
use std::{env, fs, process};

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: upper IN OUT");
        process::exit(2);
    }
    let text = match fs::read_to_string(&args[1]) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("upper: {}: {}", args[1], e);
            process::exit(1);
        }
    };
    if let Err(e) = fs::write(&args[2], text.to_uppercase().as_bytes()) {
        eprintln!("upper: {}: {}", args[2], e);
        process::exit(1);
    }
    println!("{}", text.lines().count());
}
